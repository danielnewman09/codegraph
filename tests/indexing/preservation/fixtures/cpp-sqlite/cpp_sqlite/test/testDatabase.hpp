#ifndef DATABASE_TEST_HPP
#define DATABASE_TEST_HPP

#include <gtest/gtest.h>
#include <filesystem>
#include <string>
#include "cpp_sqlite/src/utils/Logger.hpp"


class DatabaseTest : public ::testing::Test
{
public:
  ~DatabaseTest() = default;

protected:
  void SetUp() override;
  void CleanUp(std::string_view dbFile);

private:
  const static inline std::string testLogFile = "test_database.log";
};

#endif  // DATABASE_TEST_HPP