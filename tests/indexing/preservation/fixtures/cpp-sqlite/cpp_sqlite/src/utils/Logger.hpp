#ifndef LOGGER_HPP
#define LOGGER_HPP

#include <format>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

#include <spdlog/sinks/basic_file_sink.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

namespace cpp_sqlite
{

class Logger
{
public:
  // Delete copy constructor and assignment operator
  Logger(const Logger&) = delete;
  Logger& operator=(const Logger&) = delete;

  // Delete move constructor and assignment operator
  Logger(Logger&& logger) = delete;
  Logger& operator=(Logger&& rhs) = delete;

  // Get the singleton instance
  static Logger& getInstance()
  {
    static Logger instance;
    return instance;
  }

  // Configure logger with file and console output
  void configure(const std::string& loggerName = "cpp_sqlite",
                 const std::string& logFile = "cpp_sqlite.log",
                 spdlog::level::level_enum level = spdlog::level::info);

  // Set log level
  void setLevel(spdlog::level::level_enum level);

  // Check if logger is configured
  [[nodiscard]] bool isConfigured() const;

  // Get reference to the logger
  [[nodiscard]] std::shared_ptr<spdlog::logger> getLogger() const;

private:
  Logger();
  ~Logger() = default;

  std::shared_ptr<spdlog::logger> logger_;
};


}  // namespace cpp_sqlite

// Macro for safe logging with logger pointer, level, and variadic arguments
// Usage: LOG_SAFE(pLogger, spdlog::level::info, "Message with {} args", value)
#define LOG_SAFE(logger_ptr, level, ...)                          \
  if ((logger_ptr) != nullptr && (logger_ptr)->should_log(level)) \
  (logger_ptr)->log(level, __VA_ARGS__)

#endif  // LOGGER_HPP