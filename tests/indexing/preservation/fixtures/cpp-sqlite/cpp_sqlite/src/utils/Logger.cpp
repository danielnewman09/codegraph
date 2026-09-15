#include "Logger.hpp"

namespace cpp_sqlite
{
Logger::Logger() : logger_{nullptr}
{
  // Configure with default settings on construction
  configure();
}

void Logger::configure(const std::string& loggerName,
                       const std::string& logFile,
                       spdlog::level::level_enum level)
{
  // Validate inputs
  if (loggerName.empty())
  {
    throw std::invalid_argument("Logger name cannot be empty");
  }
  if (logFile.empty())
  {
    throw std::invalid_argument("Log file path cannot be empty");
  }

  try
  {
    // Unregister existing logger if it exists
    if (logger_)
    {
      spdlog::drop(logger_->name());
      logger_.reset();
    }

    // Create console sink
    auto consoleSink = std::make_shared<spdlog::sinks::stdout_color_sink_mt>();
    consoleSink->set_level(level);
    consoleSink->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%^%l%$] %v");

    // Create file sink
    auto fileSink =
      std::make_shared<spdlog::sinks::basic_file_sink_mt>(logFile, true);
    fileSink->set_level(level);
    fileSink->set_pattern("[%Y-%m-%d %H:%M:%S.%e] [%n] [%l] [thread %t] %v");

    // Create logger with both sinks
    std::vector<spdlog::sink_ptr> sinks = {consoleSink, fileSink};
    logger_ =
      std::make_shared<spdlog::logger>(loggerName, sinks.begin(), sinks.end());

    logger_->set_level(level);
    logger_->flush_on(spdlog::level::warn);

    // Register with spdlog
    spdlog::register_logger(logger_);
  }
  catch (const spdlog::spdlog_ex& ex)
  {
    logger_.reset();
    throw std::runtime_error("Logger configuration failed: " +
                             std::string(ex.what()));
  }
  catch (const std::exception& ex)
  {
    logger_.reset();
    throw std::runtime_error("Logger configuration failed: " +
                             std::string(ex.what()));
  }
}

void Logger::setLevel(spdlog::level::level_enum level)
{
  if (logger_)
  {
    logger_->set_level(level);
  }
}

bool Logger::isConfigured() const
{
  return logger_ != nullptr;
}

std::shared_ptr<spdlog::logger> Logger::getLogger() const
{
  if (!logger_)
  {
    throw std::runtime_error("Logger not configured");
  }
  return logger_;
}
}  // namespace cpp_sqlite