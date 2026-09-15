#include <stdexcept>

#include "cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp"
#include "cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"

namespace cpp_sqlite
{

Database::Database(std::string url,
                   bool allowWrite,
                   std::shared_ptr<spdlog::logger> pLogger)
  : db_(nullptr, sqlite3_close), pLogger_{pLogger}
{
  if (pLogger_)
  {
    pLogger->debug("Creating database with url: {}", url);
  }

  sqlite3* rawDb = nullptr;

  // Determine flags based on allowWrite parameter
  const int flags = allowWrite ? (SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE)
                               : SQLITE_OPEN_READONLY;

  // Open the database
  const int result = sqlite3_open_v2(url.c_str(), &rawDb, flags, nullptr);

  if (result != SQLITE_OK)
  {
    std::string errorMsg = "Failed to open database file " + url + ": ";
    if (rawDb != nullptr)
    {
      errorMsg += sqlite3_errmsg(rawDb);
      sqlite3_close(rawDb);
    }
    else
    {
      errorMsg += "Unknown error";
    }
    throw std::runtime_error(errorMsg);
  }

  // Transfer ownership to unique_ptr
  db_.reset(rawDb);
}

sqlite3& Database::getRawDB()
{
  return *db_;
}

bool Database::isInTransaction() const
{
  // sqlite3_get_autocommit returns 0 if a transaction is active
  return sqlite3_get_autocommit(db_.get()) == 0;
}

void Database::flushAllDAOs()
{
  for (auto* dao : daoCreationOrder_)
  {
    dao->insert();
  }
}

}  // namespace cpp_sqlite