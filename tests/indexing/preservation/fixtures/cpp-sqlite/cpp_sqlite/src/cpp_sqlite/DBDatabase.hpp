
#ifndef DB_DATABASE_HPP
#define DB_DATABASE_HPP

#include <any>
#include <memory>
#include <string>
#include <typeindex>
#include <unordered_map>
#include <vector>

#include <boost/describe.hpp>
#include <boost/mp11.hpp>
#include <boost/unordered_map.hpp>

#include <boost/type_index.hpp>
#include "sqlite3.h"

#include "cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBDAOBase.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"
#include "cpp_sqlite/src/utils/Logger.hpp"
#include "cpp_sqlite/src/utils/StringUtils.hpp"

namespace cpp_sqlite
{

// Forward declaration for Transaction
class Transaction;


template <ValidTransferObject T>
class DataAccessObject;


class Database
{
public:
  /*!
   * \brief Create a SQLite database with a given
   *        url and specify whether we allow read
   *        and write operations
   * \param url The string url to pass to the
   *        sqlite constructor
   * \param allowWrite The boolean indicating
   *        whether this is a read-only database.
   */
  Database(std::string url,
           bool allowWrite,
           std::shared_ptr<spdlog::logger> pLogger = nullptr);

  /*!
   * \brief Get or create a DAO for the specified type
   */
  template <ValidTransferObject T>
  DataAccessObject<T>& getDAO()
  {
    auto typeIdx = std::type_index(typeid(T));
    auto it = daos_.find(typeIdx);

    if (it == daos_.end())
    {
      auto dao = std::make_unique<DataAccessObject<T>>(*this, pLogger_);
      auto& daoRef = *dao;
      daoCreationOrder_.push_back(dao.get());
      daos_.try_emplace(typeIdx, std::move(dao));
      return daoRef;
    }

    // Safe static_cast - we know the type from the map key
    return static_cast<DataAccessObject<T>&>(*it->second);
  }

  /*!
   * \brief Flush all buffered records from all registered DAOs
   *
   * Iterates over all DataAccessObject instances created via getDAO<T>()
   * and calls insert() on each to flush their write buffers to the database.
   *
   * Thread-safe: Can be called while other threads add records via addToBuffer().
   *
   * \note This is a convenience method equivalent to calling dao.insert()
   *       on each DAO individually. The flush order is deterministic
   *       (creation order of DAOs).
   */
  void flushAllDAOs();

  /*!
   * \brief Perform a generic SELECT operation
   * \return Vector of objects matching the query
   */
  template <ValidTransferObject T>
  std::vector<T> select(PreparedSQLStmt& stmt)
  {
    std::vector<T> results;

    // Execute the query and iterate through results
    while (sqlite3_step(stmt.get()) == SQLITE_ROW)
    {
      T obj;
      int columnIndex = 0;

      // Process public members to read column values
      boost::mp11::mp_for_each<boost::describe::describe_members<
        T,
        boost::describe::mod_inherited | boost::describe::mod_public>>(
        [&](auto D)
        {
          using memberType = std::remove_cv_t<
            std::remove_reference_t<decltype(std::declval<T>().*D.pointer)>>;

          // Handle ForeignKey - just read the ID, don't load the object
          if constexpr (IsForeignKey<memberType>)
          {
            auto& fk = obj.*D.pointer;
            fk.id = static_cast<uint32_t>(
              sqlite3_column_int64(stmt.get(), columnIndex));
            columnIndex++;
          }
          // Handle repeated field transfer objects (junction tables)
          else if constexpr (IsRepeatedFieldTransferObject<memberType>)
          {
            // Load repeated fields from junction table
            auto& repeatedFieldObj = obj.*D.pointer;
            using fieldType = RepeatedFieldOfType<memberType>;

            // Build the query to get related IDs from junction table
            auto memberName = getDAO<T>().getTableName();
            const std::string dataName = stripNamespace(
              boost::typeindex::type_id<fieldType>().pretty_name());
            std::string junctionQuery = "SELECT " + dataName + "_id FROM " +
                                        memberName + "_" + dataName +
                                        " WHERE " + memberName + "_id = ?;";

            LOG_SAFE(pLogger_,
                     spdlog::level::debug,
                     "Junction query: {}",
                     junctionQuery);

            // Prepare and execute junction table query
            sqlite3_stmt* rawPtr = nullptr;
            const int result = sqlite3_prepare_v2(
              db_.get(), junctionQuery.c_str(), -1, &rawPtr, nullptr);

            if (result == SQLITE_OK)
            {
              // Bind the parent object's ID
              sqlite3_bind_int64(rawPtr, 1, static_cast<sqlite3_int64>(obj.id));

              // Collect all child IDs
              std::vector<uint32_t> childIds;
              while (sqlite3_step(rawPtr) == SQLITE_ROW)
              {
                childIds.push_back(
                  static_cast<uint32_t>(sqlite3_column_int64(rawPtr, 0)));
              }

              // Load each child object by ID
              auto& childDAO = getDAO<fieldType>();
              for (uint32_t childId : childIds)
              {
                auto childObj = childDAO.selectById(childId);
                if (childObj.has_value())
                {
                  repeatedFieldObj.data.push_back(std::move(childObj.value()));
                }
              }
            }

            sqlite3_finalize(rawPtr);
          }
          else if constexpr (ValidTransferObject<memberType>)
          {
            // For nested transfer objects, recursively load the object
            auto& nestedObj = obj.*D.pointer;
            if constexpr (isIntegral<decltype(nestedObj.id)>)
            {
              // Read the foreign key ID from the column
              auto nestedId = static_cast<uint32_t>(
                sqlite3_column_int64(stmt.get(), columnIndex));

              // Recursively load the nested object by ID
              auto& nestedDAO = getDAO<memberType>();
              auto loadedObj = nestedDAO.selectById(nestedId);
              if (loadedObj.has_value())
              {
                nestedObj = std::move(loadedObj.value());
              }
              else
              {
                // If not found, just set the ID
                nestedObj.id = nestedId;
              }
            }
            columnIndex++;
          }
          else if constexpr (isIntegral<memberType>)
          {
            obj.*D.pointer = static_cast<memberType>(
              sqlite3_column_int64(stmt.get(), columnIndex));
            columnIndex++;
          }
          else if constexpr (floatingPoint<memberType>)
          {
            obj.*D.pointer = static_cast<memberType>(
              sqlite3_column_double(stmt.get(), columnIndex));
            columnIndex++;
          }
          else if constexpr (isString<memberType>)
          {
            const unsigned char* text =
              sqlite3_column_text(stmt.get(), columnIndex);
            if (text)
            {
              obj.*D.pointer = std::string(reinterpret_cast<const char*>(text));
            }
            columnIndex++;
          }
          else if constexpr (isBlob<memberType>)
          {
            const void* blobData = sqlite3_column_blob(stmt.get(), columnIndex);
            const int blobSize = sqlite3_column_bytes(stmt.get(), columnIndex);

            if (blobData && blobSize > 0)
            {
              const auto* data = static_cast<const uint8_t*>(blobData);
              obj.*D.pointer = std::vector<uint8_t>(data, data + blobSize);
            }
            columnIndex++;
          }
        });

      results.push_back(std::move(obj));
    }

    // Reset the statement for potential reuse
    sqlite3_reset(stmt.get());

    return results;
  }

  /*!
   * \brief Perform a generic insert operation
   */
  template <ValidTransferObject T>
  bool insert(PreparedSQLStmt& stmt, T& data)
  {
    // Reset the statement for reuse
    sqlite3_reset(stmt.get());

    // Track parameter index (SQLite uses 1-based indexing)
    int paramIndex = 1;

    // Process public members
    boost::mp11::mp_for_each<boost::describe::describe_members<
      T,
      boost::describe::mod_inherited | boost::describe::mod_public>>(
      [&](auto D)
      {
        // Get member type and map to SQL type
        using memberType = std::remove_cv_t<
          std::remove_reference_t<decltype(std::declval<T>().*D.pointer)>>;

        // Handle ForeignKey - just bind the ID, no recursive insert
        if constexpr (IsForeignKey<memberType>)
        {
          const auto& fk = data.*D.pointer;
          sqlite3_bind_int64(
            stmt.get(), paramIndex, static_cast<sqlite3_int64>(fk.id));
          paramIndex++;
        }
        // If the field is, itself, another transfer object, we will
        // (1) insert the object into its own table
        // (2) insert the ID of the created object into this table
        else if constexpr (ValidTransferObject<memberType>)
        {
          // Bind the ID of the nested object
          auto& nestedObj = data.*D.pointer;

          getDAO<memberType>().insert(nestedObj);

          if constexpr (isIntegral<decltype(nestedObj.id)>)
          {
            sqlite3_bind_int64(
              stmt.get(), paramIndex, static_cast<sqlite3_int64>(nestedObj.id));
          }
          paramIndex++;
        }
        else if constexpr (IsRepeatedFieldTransferObject<memberType>)
        {
          auto& repeatedFieldObj = data.*D.pointer;
          using fieldType = RepeatedFieldOfType<memberType>;

          auto memberName = getDAO<T>().getTableName();
          const std::string dataName = stripNamespace(
            boost::typeindex::type_id<fieldType>().pretty_name());
          std::string mapTable = "INSERT INTO " + memberName + "_" + dataName +
                                 "(" + memberName + "_id, " + dataName +
                                 "_id) VALUES (?, ?);";

          sqlite3_stmt* rawPtr = nullptr;
          sqlite3_prepare_v2(db_.get(), mapTable.c_str(), -1, &rawPtr, nullptr);


          for (auto& repeatedFieldData : repeatedFieldObj.data)
          {
            getDAO<fieldType>().insert(repeatedFieldData);


            LOG_SAFE(pLogger_,
                     spdlog::level::debug,
                     "Binding data ID: {}, and fieldID: {}",
                     data.id,
                     repeatedFieldData.id);

            sqlite3_bind_int64(rawPtr, 1, static_cast<sqlite3_int64>(data.id));
            sqlite3_bind_int64(
              rawPtr, 2, static_cast<sqlite3_int64>(repeatedFieldData.id));

            // Execute the statement
            int result = sqlite3_step(rawPtr);

            if (result != SQLITE_DONE)
            {
              LOG_SAFE(pLogger_,
                       spdlog::level::err,
                       "Insert failed with code: {}",
                       result);
            }

            // Reset the statement for reuse
            sqlite3_reset(rawPtr);
          }
          sqlite3_finalize(rawPtr);
          // do nothing - paramIndex stays the same as repeated fields don't add
          // columns to parent table
        }
        else
        {
          const auto& value = data.*D.pointer;

          if constexpr (isIntegral<memberType>)
          {
            sqlite3_bind_int64(
              stmt.get(), paramIndex, static_cast<sqlite3_int64>(value));
            paramIndex++;
          }
          else if constexpr (floatingPoint<memberType>)
          {
            sqlite3_bind_double(
              stmt.get(), paramIndex, static_cast<double>(value));
            paramIndex++;
          }
          else if constexpr (std::is_same_v<memberType, std::string>)
          {
            sqlite3_bind_text(stmt.get(),
                              paramIndex,
                              value.c_str(),
                              static_cast<int>(value.length()),
                              SQLITE_TRANSIENT);
            paramIndex++;
          }
          else if constexpr (isBlob<memberType>)
          {
            sqlite3_bind_blob(stmt.get(),
                              paramIndex,
                              value.data(),
                              static_cast<int>(value.size()),
                              SQLITE_TRANSIENT);
            paramIndex++;
          }
          else
          {
            // For unknown types, bind as null
            sqlite3_bind_null(stmt.get(), paramIndex);
            paramIndex++;
          }
        }
      });

    // Execute the statement
    int result = sqlite3_step(stmt.get());

    if (result != SQLITE_DONE)
    {
      LOG_SAFE(
        pLogger_, spdlog::level::err, "Insert failed with code: {}", result);
    }

    return result == SQLITE_DONE;
  }

  /*!
   * \brief Get raw SQLite database pointer for direct access
   * \return Raw sqlite3* pointer
   */
  sqlite3& getRawDB();

  /*!
   * \brief Check if a transaction is currently active
   * \return true if a transaction is active (autocommit is disabled)
   */
  [[nodiscard]] bool isInTransaction() const;

  /*!
   * \brief Execute a function within a transaction
   *
   * This is a convenience method that wraps a function in a transaction.
   * If the function throws an exception, the transaction is rolled back.
   * If the function completes successfully, the transaction is committed.
   *
   * \param func The function to execute within the transaction
   * \throws TransactionError if transaction operations fail
   * \throws Any exception thrown by the function (after rollback)
   *
   * Usage:
   * \code
   *   db.withTransaction([&]() {
   *     auto& dao = db.getDAO<MyObject>();
   *     dao.insert(obj1);
   *     dao.insert(obj2);
   *   });
   * \endcode
   */
  template <typename Func>
  void withTransaction(Func&& func);

private:
  //!< The unique pointer storing the SQLite database
  //!< object
  std::unique_ptr<sqlite3, decltype(&sqlite3_close)> db_;

  //! The pointer to the spdlog for this object.
  std::shared_ptr<spdlog::logger> pLogger_;

  //! DAO storage using boost::unordered_map for better performance
  boost::unordered_map<std::type_index, std::unique_ptr<DAOBase>> daos_;

  //! Tracks DAO creation order for deterministic iteration in flushAllDAOs()
  std::vector<DAOBase*> daoCreationOrder_;
};

// Implementation of ForeignKey::resolve() (needs Database definition)
template <ValidTransferObject T>
std::optional<std::reference_wrapper<const T>> ForeignKey<T>::resolve(
  Database& db)
{
  if (isSet() && data_ == std::nullopt)
  {
    data_ = db.getDAO<T>().selectCacheById(id);
  }

  return data_;
}

}  // namespace cpp_sqlite

// Include Transaction header after Database is fully defined
#include "cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp"

namespace cpp_sqlite
{

template <typename Func>
void Database::withTransaction(Func&& func)
{
  Transaction txn(*this);
  func();
  txn.commit();
}

}  // namespace cpp_sqlite

#endif  // DB_DATABASE_HPP