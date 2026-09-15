#ifndef DB_TRANSACTION_HPP
#define DB_TRANSACTION_HPP

#include <cstdint>
#include <stdexcept>
#include <string>

namespace cpp_sqlite
{

// Forward declaration
class Database;

/*!
 * \brief Exception thrown when a transaction operation fails
 */
class TransactionError : public std::runtime_error
{
public:
  explicit TransactionError(const std::string& message)
    : std::runtime_error(message)
  {
  }
};

/*!
 * \brief RAII-style transaction management for SQLite database operations.
 *
 * This class provides automatic transaction management with the following
 * features:
 * - Automatic rollback if the transaction is not explicitly committed
 * - Support for nested transactions via savepoints
 * - Exception-safe resource management
 *
 * Usage:
 * \code
 *   Database db("test.db", true);
 *   {
 *     Transaction txn(db);
 *     // ... perform database operations ...
 *     txn.commit();  // Explicit commit
 *   }
 *   // If commit() is not called, destructor will rollback
 * \endcode
 *
 * For nested transactions:
 * \code
 *   Database db("test.db", true);
 *   {
 *     Transaction outer(db);
 *     // ... some operations ...
 *     {
 *       Transaction inner(db);  // Creates a savepoint
 *       // ... more operations ...
 *       inner.commit();  // Releases savepoint
 *     }
 *     outer.commit();
 *   }
 * \endcode
 */
class Transaction
{
public:
  /*!
   * \brief Begin a new transaction
   * \param db Reference to the database
   * \throws TransactionError if BEGIN fails
   *
   * If a transaction is already active, this creates a savepoint instead.
   */
  explicit Transaction(Database& db);

  /*!
   * \brief Destructor - automatically rolls back if not committed
   */
  ~Transaction() noexcept;

  // Non-copyable
  Transaction(const Transaction&) = delete;
  Transaction& operator=(const Transaction&) = delete;

  // Movable
  Transaction(Transaction&& other) noexcept;
  Transaction& operator=(Transaction&& other) noexcept;

  /*!
   * \brief Commit the transaction
   * \throws TransactionError if COMMIT fails
   *
   * After calling commit(), the destructor will not rollback.
   * For savepoints, this releases the savepoint.
   */
  void commit();

  /*!
   * \brief Explicitly rollback the transaction
   * \throws TransactionError if ROLLBACK fails
   *
   * After calling rollback(), the destructor will not attempt another
   * rollback. For savepoints, this rolls back to the savepoint.
   */
  void rollback();

  /*!
   * \brief Check if the transaction is still active (not committed or rolled
   * back)
   * \return true if the transaction is active
   */
  [[nodiscard]] bool isActive() const noexcept
  {
    return isActive_;
  }

  /*!
   * \brief Check if this is a savepoint (nested transaction)
   * \return true if this is a savepoint
   */
  [[nodiscard]] bool isSavepoint() const noexcept
  {
    return isSavepoint_;
  }

  /*!
   * \brief Get the savepoint name (empty if not a savepoint)
   * \return The savepoint name
   */
  [[nodiscard]] const std::string& getSavepointName() const noexcept
  {
    return savepointName_;
  }

private:
  //! Execute a SQL statement and handle errors
  void executeSQL(const std::string& sql);

  //! Reference to the database
  Database* db_;

  //! Whether this transaction is still active
  bool isActive_;

  //! Whether this is a savepoint (nested transaction)
  bool isSavepoint_;

  //! The savepoint name (if this is a savepoint)
  std::string savepointName_;

  //! Static counter for generating unique savepoint names
  static inline uint32_t savepointCounter_{0};
};

}  // namespace cpp_sqlite

#endif  // DB_TRANSACTION_HPP
