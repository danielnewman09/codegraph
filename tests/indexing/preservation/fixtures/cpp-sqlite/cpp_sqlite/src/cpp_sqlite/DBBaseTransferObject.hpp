#ifndef BASE_TRANSFER_OBJECT_HPP
#define BASE_TRANSFER_OBJECT_HPP

#include <cstdint>
#include <limits>

#include <boost/describe.hpp>
#include <boost/describe/class.hpp>

namespace cpp_sqlite
{

/*!
 * \brief The fundamental transfer object for SQL operations
 *
 * The Base Transfer Object simply contains an identifier, used
 * for SQL operations and assumed to be the primary key for the
 * associated table. Any subsequent transfer object should inherit
 * from this to enforce the primary key behavior.
 */
struct BaseTransferObject
{
  //! The unique identifier for the base Transfer object
  uint32_t id = std::numeric_limits<uint32_t>::max();
};

// Register the base transfer object with
// boost::describe
BOOST_DESCRIBE_STRUCT(BaseTransferObject, (), (id));

}  // namespace cpp_sqlite

#endif  // BASE_TRANSFER_OBJECT_HPP