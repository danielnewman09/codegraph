#include "cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp"

#include "cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"
#include "sqlite3.h"

namespace cpp_sqlite
{

Transaction::Transaction(Database& db)
  : db_(&db), isActive_(false), isSavepoint_(false), savepointName_()
{
  // Check if a transaction is already active
  // sqlite3_get_autocommit returns 0 if a transaction is active
  if (sqlite3_get_autocommit(&db_->getRawDB()) == 0)
  {
    // A transaction is already active - create a savepoint
    isSavepoint_ = true;
    savepointName_ = "sp_" + std::to_string(++savepointCounter_);
    executeSQL("SAVEPOINT " + savepointName_);
  }
  else
  {
    // No active transaction - begin a new one
    executeSQL("BEGIN TRANSACTION");
  }

  isActive_ = true;
}

Transaction::~Transaction() noexcept
{
  if (isActive_)
  {
    try
    {
      rollback();
    }
    catch (...)
    {
      // Destructor must not throw - swallow any exceptions
    }
  }
}

Transaction::Transaction(Transaction&& other) noexcept
  : db_(other.db_),
    isActive_(other.isActive_),
    isSavepoint_(other.isSavepoint_),
    savepointName_(std::move(other.savepointName_))
{
  other.db_ = nullptr;
  other.isActive_ = false;
}

Transaction& Transaction::operator=(Transaction&& other) noexcept
{
  if (this != &other)
  {
    // Rollback current transaction if active
    if (isActive_)
    {
      try
      {
        rollback();
      }
      catch (...)
      {
        // Swallow exceptions
      }
    }

    db_ = other.db_;
    isActive_ = other.isActive_;
    isSavepoint_ = other.isSavepoint_;
    savepointName_ = std::move(other.savepointName_);

    other.db_ = nullptr;
    other.isActive_ = false;
  }
  return *this;
}

void Transaction::commit()
{
  if (!isActive_)
  {
    throw TransactionError("Cannot commit: transaction is not active");
  }

  if (isSavepoint_)
  {
    executeSQL("RELEASE SAVEPOINT " + savepointName_);
  }
  else
  {
    executeSQL("COMMIT");
  }

  isActive_ = false;
}

void Transaction::rollback()
{
  if (!isActive_)
  {
    throw TransactionError("Cannot rollback: transaction is not active");
  }

  if (isSavepoint_)
  {
    executeSQL("ROLLBACK TO SAVEPOINT " + savepointName_);
    // Also release the savepoint after rollback
    executeSQL("RELEASE SAVEPOINT " + savepointName_);
  }
  else
  {
    executeSQL("ROLLBACK");
  }

  isActive_ = false;
}

void Transaction::executeSQL(const std::string& sql)
{
  char* errMsg = nullptr;
  const int result =
    sqlite3_exec(&db_->getRawDB(), sql.c_str(), nullptr, nullptr, &errMsg);

  if (result != SQLITE_OK)
  {
    std::string error = "Transaction SQL failed: ";
    if (errMsg != nullptr)
    {
      error += errMsg;
      sqlite3_free(errMsg);
    }
    else
    {
      error += "Unknown error (code: " + std::to_string(result) + ")";
    }
    throw TransactionError(error);
  }
}

}  // namespace cpp_sqlite
