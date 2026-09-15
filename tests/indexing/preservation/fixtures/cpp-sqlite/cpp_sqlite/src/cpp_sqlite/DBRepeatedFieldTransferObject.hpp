#ifndef REPEATED_FIELD_TRANSFER_OBJECT_HPP
#define REPEATED_FIELD_TRANSFER_OBJECT_HPP

#include <vector>

#include <boost/describe.hpp>
#include <boost/describe/class.hpp>

#include "cpp_sqlite/src/cpp_sqlite/DBTraits.hpp"

namespace cpp_sqlite
{

/*!
 * \brief Container for repeated (one-to-many) fields in transfer objects
 *
 * This represents a collection of transfer objects that forms a one-to-many
 * relationship in the database (typically requiring a junction table).
 *
 * \tparam T Must be a SingleTransferObject (not another RepeatedField)
 *
 * Example usage:
 * \code
 * struct Tag : BaseTransferObject { std::string name; };
 * struct Article : BaseTransferObject {
 *   std::string title;
 *   RepeatedFieldTransferObject<Tag> tags;  // One-to-many relationship
 * };
 * \endcode
 *
 * The constraint SingleTransferObject ensures you cannot nest repeated fields:
 * RepeatedFieldTransferObject<RepeatedFieldTransferObject<Tag>> // Compile
 * error!
 */
template <ValidTransferObject T>
struct RepeatedFieldTransferObject
{
  //!< The underlying vector of transfer objects
  //!< Member must be named 'data' for compatibility with boost::describe
  std::vector<T> data;
};


}  // namespace cpp_sqlite

#endif  // REPEATED_FIELD_TRANSFER_OBJECT_HPP