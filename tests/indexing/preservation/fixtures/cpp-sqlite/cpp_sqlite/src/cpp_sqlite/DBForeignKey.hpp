#ifndef DB_FOREIGN_KEY_HPP
#define DB_FOREIGN_KEY_HPP

#include <cstdint>
#include <optional>

#include <boost/describe.hpp>

#include "cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"

namespace cpp_sqlite
{

// Forward declarations
class Database;

// Import ValidTransferObject concept from DBTraits.hpp
// (will be included after this file to avoid circular dependency)

/*!
 * \brief ForeignKey<T> stores only the ID of a related object T
 *
 * This allows lazy loading - the full object is not loaded from the database
 * until explicitly requested via the resolve() method.
 *
 * Use this when you want to reference another table without the overhead
 * of loading the full nested object during SELECT operations.
 *
 * Example:
 * \code
 * struct Vertex3D : public cpp_sqlite::BaseTransferObject {
 *     float x, y, z;
 * };
 *
 * struct RigidBody : public cpp_sqlite::BaseTransferObject {
 *     std::string name;
 *     ForeignKey<Vertex3D> centerOfMass;  // Lazy - just stores ID
 *     Vertex3D position;                   // Eager - auto-loads full object
 * };
 *
 * // Usage:
 * auto body = bodyDAO.selectById(1);
 * std::cout << "Center FK ID: " << body->centerOfMass.id << "\n";
 *
 * // Load the full vertex only when needed
 * auto vertex = body->centerOfMass.resolve(db);
 * if (vertex) {
 *     std::cout << "Center: " << vertex->x << ", " << vertex->y << "\n";
 * }
 * \endcode
 */
template <ValidTransferObject T>
struct ForeignKey
{
  //! The ID of the referenced object
  uint32_t id{0};

  // The data stored in the foreign key table - loaded on demand
  std::optional<std::reference_wrapper<const T>> data_;

  /*!
   * \brief Default
    constructor - creates unset FK (id = 0)
   */
  ForeignKey() = default;

  /*!
   * \brief Construct from an ID
   */
  explicit ForeignKey(uint32_t foreignId) : id{foreignId}, data_{std::nullopt}
  {
  }

  /*!
   * \brief Resolve the foreign key to the full object
   * \param db Reference to the database
   * \return Optional containing the loaded object, or empty if not found
   */
  std::optional<std::reference_wrapper<const T>> resolve(Database& db);

  /*!
   * \brief Check if this FK is set (non-zero ID)
   */
  [[nodiscard]] bool isSet() const
  {
    return id != 0;
  }
};

}  // namespace cpp_sqlite

#endif  // DB_FOREIGN_KEY_HPP
