#ifndef DATA_ACCESS_OBJECT_HPP
#define DATA_ACCESS_OBJECT_HPP

#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <typeinfo>
#include <unordered_map>
#include <vector>

#include <boost/describe.hpp>
#include <boost/describe/class.hpp>
#include <boost/mp11.hpp>
#include <boost/type_index.hpp>
#include "sqlite3.h"

#include "cpp_sqlite/src/cpp_sqlite/DBDAOBase.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"
#include "cpp_sqlite/src/utils/Logger.hpp"
#include "cpp_sqlite/src/utils/StringUtils.hpp"

namespace cpp_sqlite
{

class Database;

template <ValidTransferObject T>
class DataAccessObject : public DAOBase
{
public:
  /*!
   * Construct a data access object for this
   * database
   */
  explicit DataAccessObject(Database& database,
                            std::shared_ptr<spdlog::logger> pLogger = nullptr)
    : tableName_{stripNamespace(boost::typeindex::type_id<T>().pretty_name())},
      insertStmt_{nullptr, sqlite3_finalize},
      selectAllStmt_{nullptr, sqlite3_finalize},
      selectByIdStmt_{nullptr, sqlite3_finalize},
      db_{database},
      pLogger_{std::move(pLogger)}
  {
    isInitialized_ &= executeCreateStmt();
    isInitialized_ &= prepareInsertStatement();
    isInitialized_ &= prepareSelectStatements();
  }

  [[nodiscard]] std::string getTableName() const override
  {
    return tableName_;
  }

  /*!
   * \brief Get the initialization status of this DAO
   * \return The initialization status of the object.
   */
  [[nodiscard]] bool isInitialized() const override
  {
    return isInitialized_;
  }

  bool insert(T& data)
  {
    if (!insertStmt_)
    {
      return false;
    }

    if (data.id == std::numeric_limits<uint32_t>::max())
    {
      data.id = incrementIdCounter();
    }
    // If the ID has been manually specified by the user without using
    // the class-given `incrementIdCounter()` function, we want to log
    // an error and fail to execute the insert.
    else if (data.id <= idCounter_)
    {
      LOG_SAFE(pLogger_,
               spdlog::level::err,
               "The identifier for this transfer object has been manually set "
               "outside of the context of the DataAccessObject");
      return false;
    }
    else
    {
      // Manual ID is valid and higher than counter - update counter to prevent
      // conflicts
      LOG_SAFE(pLogger_,
               spdlog::level::warn,
               "Manual ID {} is higher than current counter {}. Updating "
               "counter to prevent future conflicts.",
               data.id,
               idCounter_);
      idCounter_ = data.id;
    }


    return db_.insert(insertStmt_, data);
  }

  /*!
   * \brief Perform an insert with the buffer data
   * Thread-safe: Swaps buffers under lock, then processes without lock
   */
  void insert() override
  {
    // Swap the write and flush buffers under a lock
    {
      std::scoped_lock<std::mutex> lock(bufferMutex_);
      std::swap(writeBuffer_, flushBuffer_);
    }

    // Now process flushBuffer_ without holding the lock
    // Writers can continue adding to writeBuffer_ in parallel
    bool success = true;
    for (auto& item : flushBuffer_)
    {
      success &= insert(item);
    }

    // Clear the flush buffer after processing
    flushBuffer_.clear();
  }

  /*!
   * \brief Clear the data buffer
   */
  void clearBuffer() override
  {
    std::scoped_lock<std::mutex> lock(bufferMutex_);
    writeBuffer_.clear();
    flushBuffer_.clear();
  }

  /*!
   * \brief Add object to buffer for insertion (thread-safe)
   * This can be called from any thread
   */
  void addToBuffer(const T& obj)
  {
    std::scoped_lock<std::mutex> lock(bufferMutex_);
    writeBuffer_.push_back(obj);
  }

  /*!
   * \brief Select all records from the table
   * \return Vector of all objects in the table
   */
  std::vector<T> selectAll()
  {
    if (!selectAllStmt_)
    {
      LOG_SAFE(
        pLogger_, spdlog::level::err, "selectAll statement not prepared");
      return {};
    }

    return db_.select<T>(selectAllStmt_);
  }

  std::optional<std::reference_wrapper<const T>> selectCacheById(uint32_t id)
  {
    // Check if already loaded in cache
    auto resultIt = selectCache_.find(id);
    if (resultIt != selectCache_.end())
    {
      return std::cref(resultIt->second);
    }

    auto selectResult = selectById(id);

    if (!selectResult.has_value())
    {
      return std::nullopt;
    }

    auto result = selectCache_.emplace(id, std::move(selectResult.value()));
    return std::cref(result.first->second);
  }

  /*!
   * \brief Select a single record by ID
   * \param id The ID of the record to retrieve
   * \return Optional containing the object if found, empty otherwise
   */
  std::optional<T> selectById(uint32_t id)
  {
    if (!selectByIdStmt_)
    {
      LOG_SAFE(
        pLogger_, spdlog::level::err, "selectById statement not prepared");
      return std::nullopt;
    }

    // Reset and bind the ID parameter
    sqlite3_reset(selectByIdStmt_.get());
    sqlite3_bind_int64(
      selectByIdStmt_.get(), 1, static_cast<sqlite3_int64>(id));

    auto results = db_.select<T>(selectByIdStmt_);

    if (results.empty())
    {
      return std::nullopt;
    }

    return results[0];
  }

  uint32_t incrementIdCounter()
  {
    return ++idCounter_;
  }

private:
  // Helper function to map C++ types to SQL types
  template <isSupportedDBType FieldType>
  constexpr std::string getSQLType()
  {
    if constexpr (isIntegral<FieldType>)
    {
      return "INTEGER";
    }
    else if constexpr (floatingPoint<FieldType>)
    {
      return "FLOAT";
    }
    else if constexpr (std::is_same_v<FieldType, std::string>)
    {
      return "TEXT";
    }
    else
    {
      return "BLOB";
    }
  }

  /*!
   * \brief Create the string that is used to generate the SQL
   *        CREATE TABLE command
   * \return A string for the table creation command.
   */
  std::string generateCreateTableSQL()
  {
    std::string sql{};
    sql = "CREATE TABLE IF NOT EXISTS " + tableName_ + " (";
    std::string foreignKeys;

    bool first = true;

    // Process public and inherited members
    boost::mp11::mp_for_each<boost::describe::describe_members<
      T,
      boost::describe::mod_inherited | boost::describe::mod_public>>(
      [&](auto D)
      {
        // Get member type and map to SQL type
        using memberType = std::remove_cv_t<
          std::remove_reference_t<decltype(std::declval<T>().*D.pointer)>>;

        if constexpr (IsRepeatedFieldTransferObject<memberType>)
        {
          using fieldType = RepeatedFieldOfType<memberType>;
          std::string dataName = stripNamespace(
            boost::typeindex::type_id<fieldType>().pretty_name());
          std::string mapTable = "CREATE TABLE IF NOT EXISTS " + tableName_ +
                                 "_" + dataName + "(" + tableName_ +
                                 "_id INTEGER, " + dataName + "_id INTEGER); ";

          char* errMsg = nullptr;

          LOG_SAFE(
            pLogger_, spdlog::level::trace, "Create Table: {}", mapTable);

          if (sqlite3_exec(
                &db_.getRawDB(), mapTable.c_str(), nullptr, nullptr, &errMsg) !=
              SQLITE_OK)
          {
            LOG_SAFE(pLogger_, spdlog::level::err, "SQL error: {}", errMsg);
          }
        }
        else
        {
          if (!first)
          {
            sql += ", ";
          }

          // Get member name
          sql += D.name;

          // Handle ForeignKey - treat it like a foreign key ID field
          if constexpr (IsForeignKey<memberType>)
          {
            using ReferencedType = ForeignKeyType<memberType>;
            std::string refTableName = stripNamespace(
              boost::typeindex::type_id<ReferencedType>().pretty_name());

            sql += "_id INTEGER";
            foreignKeys += ", FOREIGN KEY (" + std::string(D.name) +
                           "_id) REFERENCES " + refTableName + "(id)";
          }
          // If the field is, itself, another transfer object, we treat
          // this field in the current table as a key to the table
          // that the child object presumably exists at.
          else if constexpr (ValidTransferObject<memberType>)
          {
            using idType = decltype(std::declval<memberType>().id);
            sql += "_id " + getSQLType<idType>();

            foreignKeys +=
              ", FOREIGN KEY (" + std::string(D.name) + "_id) REFERENCES " +
              stripNamespace(
                boost::typeindex::type_id<memberType>().pretty_name()) +
              "(id)";
          }
          else if constexpr (isSupportedDBType<memberType>)
          {
            sql += " " + getSQLType<memberType>();

            // Add PRIMARY KEY for id field
            if (std::string(D.name) == "id")
            {
              sql += " PRIMARY KEY";
            }
          }

          first = false;
        }
      });

    sql += foreignKeys;

    sql += ");";
    return sql;
  }

  bool prepareSQLStatements()
  {
    return prepareInsertStatement() && prepareSelectStatements();
  }

  bool prepareInsertStatement()
  {
    std::string insertQuery = generateInsertSQL();

    LOG_SAFE(pLogger_, spdlog::level::debug, insertQuery);

    sqlite3_stmt* rawPtr = nullptr;
    int result = sqlite3_prepare_v2(
      &(db_.getRawDB()), insertQuery.c_str(), -1, &rawPtr, nullptr);

    if (result != SQLITE_OK)
    {
      LOG_SAFE(
        pLogger_,
        spdlog::level::err,
        "Could not prepare insert statement for table {}. SQLITE code: {}",
        tableName_,
        result);
      return false;
    }

    insertStmt_.reset(rawPtr);
    return true;
  }

  bool prepareSelectStatements()
  {
    // Prepare SELECT ALL statement
    std::string selectAllQuery = generateSelectAllSQL();
    LOG_SAFE(pLogger_, spdlog::level::debug, selectAllQuery);

    sqlite3_stmt* rawPtr = nullptr;
    int result = sqlite3_prepare_v2(
      &(db_.getRawDB()), selectAllQuery.c_str(), -1, &rawPtr, nullptr);

    if (result != SQLITE_OK)
    {
      LOG_SAFE(
        pLogger_,
        spdlog::level::err,
        "Could not prepare SELECT ALL statement for table {}. SQLITE code: {}",
        tableName_,
        result);
      return false;
    }

    selectAllStmt_.reset(rawPtr);

    // Prepare SELECT BY ID statement
    std::string selectByIdQuery = generateSelectByIdSQL();
    LOG_SAFE(pLogger_, spdlog::level::debug, selectByIdQuery);

    rawPtr = nullptr;
    result = sqlite3_prepare_v2(
      &(db_.getRawDB()), selectByIdQuery.c_str(), -1, &rawPtr, nullptr);

    if (result != SQLITE_OK)
    {
      LOG_SAFE(pLogger_,
               spdlog::level::err,
               "Could not prepare SELECT BY ID statement for table {}. SQLITE "
               "code: {}",
               tableName_,
               result);
      return false;
    }

    selectByIdStmt_.reset(rawPtr);
    return true;
  }

  /*!
   * \brief Generate SELECT ALL SQL statement
   * \return The SQL string for selecting all records
   */
  std::string generateSelectAllSQL()
  {
    std::ostringstream sql;
    sql << "SELECT ";

    std::vector<std::string> columns;

    // Process public members to build column list
    boost::mp11::mp_for_each<boost::describe::describe_members<
      T,
      boost::describe::mod_inherited | boost::describe::mod_public>>(
      [&](auto D)
      {
        using memberType = std::remove_cv_t<
          std::remove_reference_t<decltype(std::declval<T>().*D.pointer)>>;

        // Skip repeated field transfer objects (they're in separate tables)
        if constexpr (IsRepeatedFieldTransferObject<memberType>)
        {
          // Skip - these are handled separately
        }
        else if constexpr (IsForeignKey<memberType> ||
                           ValidTransferObject<memberType>)
        {
          // ForeignKey fields are stored as "_id" columns
          columns.push_back(std::string(D.name) + "_id");
        }
        else if constexpr (isSupportedDBType<memberType>)
        {
          columns.push_back(std::string(D.name));
        }
      });

    // Build the column names part
    bool first = true;
    for (const auto& column : columns)
    {
      if (!first)
      {
        sql << ", ";
      }
      sql << column;
      first = false;
    }

    sql << " FROM " << tableName_ << ";";
    return sql.str();
  }

  /*!
   * \brief Generate SELECT BY ID SQL statement
   * \return The SQL string for selecting a record by ID
   */
  std::string generateSelectByIdSQL()
  {
    std::ostringstream sql;
    sql << "SELECT ";

    std::vector<std::string> columns;

    // Process public members to build column list
    boost::mp11::mp_for_each<boost::describe::describe_members<
      T,
      boost::describe::mod_inherited | boost::describe::mod_public>>(
      [&](auto D)
      {
        using memberType = std::remove_cv_t<
          std::remove_reference_t<decltype(std::declval<T>().*D.pointer)>>;

        // Skip repeated field transfer objects
        if constexpr (IsRepeatedFieldTransferObject<memberType>)
        {
          // Skip - these are handled separately
        }
        else if constexpr (IsForeignKey<memberType> ||
                           ValidTransferObject<memberType>)
        {
          // ForeignKey fields are stored as "_id" columns
          columns.push_back(std::string(D.name) + "_id");
        }
        else if constexpr (isSupportedDBType<memberType>)
        {
          columns.push_back(std::string(D.name));
        }
      });

    // Build the column names part
    bool first = true;
    for (const auto& column : columns)
    {
      if (!first)
      {
        sql << ", ";
      }
      sql << column;
      first = false;
    }

    sql << " FROM " << tableName_ << " WHERE id = ?;";
    return sql.str();
  }

  /*!
   * \brief Create the string that prepares an insert statement.
   *
   * \return The string for a prepared insert statement for a DB
   *         table.
   */
  std::string generateInsertSQL()
  {
    std::ostringstream sql;
    sql << "INSERT INTO " << tableName_ << " (";

    std::vector<std::string> columns;
    std::vector<std::string> placeholders;

    // Process public members to build column list
    boost::mp11::mp_for_each<boost::describe::describe_members<
      T,
      boost::describe::mod_inherited | boost::describe::mod_public>>(
      [&](auto D)
      {
        using memberType = std::remove_cv_t<
          std::remove_reference_t<decltype(std::declval<T>().*D.pointer)>>;

        // Handle ForeignKey
        if constexpr (IsForeignKey<memberType> ||
                      ValidTransferObject<memberType>)
        {
          columns.push_back(std::string(D.name) + "_id");
          placeholders.emplace_back("?");
        }
        else if constexpr (isSupportedDBType<memberType>)
        {
          columns.push_back(std::string(D.name));
          placeholders.emplace_back("?");
        }
      });

    // Build the column names part
    bool first = true;
    for (const auto& column : columns)
    {
      if (!first)
      {
        sql << ", ";
      }
      sql << column;
      first = false;
    }

    sql << ") VALUES (";

    // Build the placeholders part
    first = true;
    for (const auto& placeholder : placeholders)
    {
      if (!first)
      {
        sql << ", ";
      }
      sql << placeholder;
      first = false;
    }

    sql << ");";
    return sql.str();
  }

  /*!
   * \brief Perform the table creation.
   * \returns a boolean indicating whether this operation was successful.
   */
  bool executeCreateStmt()
  {
    std::string createQuery = generateCreateTableSQL();

    LOG_SAFE(pLogger_, spdlog::level::trace, "Executing: {}", createQuery);
    int result = sqlite3_exec(
      &db_.getRawDB(), createQuery.c_str(), nullptr, nullptr, nullptr);
    if (result != SQLITE_OK)
    {
      LOG_SAFE(pLogger_,
               spdlog::level::err,
               "Could not execute query. Result code: {}",
               result);
      return false;
    }
    return true;
  }

  //! The name of the table accessed by this object.
  std::string tableName_;

  //!< The prepared statement to facilitate inserting data into the database
  PreparedSQLStmt insertStmt_;

  //!< The prepared statement for SELECT ALL queries
  PreparedSQLStmt selectAllStmt_;

  //!< The prepared statement for SELECT BY ID queries
  PreparedSQLStmt selectByIdStmt_;

  //! Write buffer - writers add here (protected by mutex)
  std::vector<T> writeBuffer_{};

  //! Flush buffer - DB thread reads from here (no lock needed during flush)
  std::vector<T> flushBuffer_{};

  //! The cache for stored select data
  std::unordered_map<uint32_t, T> selectCache_;

  //! Mutex protecting the write buffer
  std::mutex bufferMutex_;

  //! The current ID counter for inserting new data
  uint32_t idCounter_{0};

  //! Tracks whether or not the DAO is initialized
  bool isInitialized_{true};

  //! Reference to the Database object
  //! The Database class manages DAO lifetime through its internal storage.
  Database& db_;

  //! The local logger
  std::shared_ptr<spdlog::logger> pLogger_;
};

}  // namespace cpp_sqlite

#endif  // DATA_ACCESS_OBJECT_HPP
