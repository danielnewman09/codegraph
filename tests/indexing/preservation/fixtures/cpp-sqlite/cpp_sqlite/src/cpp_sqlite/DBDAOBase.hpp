#ifndef DB_DAO_BASE_HPP
#define DB_DAO_BASE_HPP

#include <cstdint>
#include <string>

/*!
 * Abstract base class for all Data Access Objects
 * Provides common interface for polymorphic storage
 */
class DAOBase
{
public:
  /*!
   *
   */
  enum class BaseSQLType : uint8_t
  {
    INT,
    FLOAT,
    TEXT,
    BLOB
  };

  virtual ~DAOBase() = default;

  [[nodiscard]] virtual std::string getTableName() const = 0;

  /*!
   * \brief Check if the DAO is properly initialized
   */
  [[nodiscard]] virtual bool isInitialized() const = 0;

  /*!
   * \brief Perform insert operation with buffered data
   */
  virtual void insert() = 0;

  /*!
   * \brief Clear the internal data buffer
   */
  virtual void clearBuffer() = 0;
};

#endif  // DB_DAO_BASE_HPP