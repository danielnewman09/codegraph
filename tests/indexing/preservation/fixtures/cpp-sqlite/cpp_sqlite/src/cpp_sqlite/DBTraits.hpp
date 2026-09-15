#ifndef DB_TRAITS_HPP
#define DB_TRAITS_HPP

#include <concepts>
#include <memory>
#include <type_traits>
#include <vector>

#include "sqlite3.h"

#include "cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp"

namespace cpp_sqlite
{


/*!
 * A wrapping alias for the sqlite3 prepared statement
 * that allows us to use modern C++ memory management
 * with this library.
 */
using PreparedSQLStmt =
  std::unique_ptr<sqlite3_stmt, decltype(&sqlite3_finalize)>;

// Primary concept: Must derive from BaseTransferObject
template <typename T>
concept TransferObject = std::derived_from<T, BaseTransferObject>;

// Extended concept: Must be a transfer object with default constructor
template <typename T>
concept DefaultConstructibleTransferObject =
  TransferObject<T> && std::default_initializable<T>;

// Extended concept: Must be a transfer object that's copyable
template <typename T>
concept CopyableTransferObject = TransferObject<T> && std::copyable<T>;

// Extended concept: Must be a transfer object that's movable
template <typename T>
concept MovableTransferObject = TransferObject<T> && std::movable<T>;

// Comprehensive concept combining common requirements
template <typename T>
concept ValidTransferObject =
  TransferObject<T> && DefaultConstructibleTransferObject<T>;

template <typename T>
struct IsVector : std::false_type
{
};

template <typename T, typename Allocator>
struct IsVector<std::vector<T, Allocator>> : std::true_type
{
};

template <typename T>
inline constexpr bool kIsVectorV = IsVector<T>::value;

template <ValidTransferObject T>
struct RepeatedFieldTransferObject;

template <ValidTransferObject T>
struct ForeignKey;

template <typename C>
concept IsRepeatedFieldTransferObject = requires(C c) {
  // 1. Check for a member named `data`
  { c.data };

  // 2. Check that the member `data` is a std::vector
  requires kIsVectorV<decltype(c.data)>;

  // 3. Check the element type of the vector against the HasToString concept
  requires ValidTransferObject<typename decltype(c.data)::value_type>;
};


// --- The core template trait to extract template parameters ---
// Primary template (general case)
template <typename T>
struct GetRepeatedFieldParams
{
  static constexpr bool kIsSpecialization = false;
};

// Partial specialization for `Foo<Bar>`
template <typename T>
struct GetRepeatedFieldParams<RepeatedFieldTransferObject<T>>
{
  static constexpr bool kIsSpecialization = true;
  using SpecializationType = T;
};

// --- A helper alias for cleaner syntax ---
template <IsRepeatedFieldTransferObject T>
using RepeatedFieldOfType =
  typename GetRepeatedFieldParams<T>::SpecializationType;

// --- ForeignKey Type Traits ---

// Primary template for detecting ForeignKey
template <typename T>
struct IsForeignKeyT : std::false_type
{
};

// Specialization for ForeignKey<T>
template <ValidTransferObject T>
struct IsForeignKeyT<ForeignKey<T>> : std::true_type
{
};

// Concept for detecting ForeignKey types
template <typename T>
concept IsForeignKey = IsForeignKeyT<T>::value;

// Extract the referenced type from ForeignKey
template <typename T>
struct ForeignKeyTypeT
{
};

template <ValidTransferObject T>
struct ForeignKeyTypeT<ForeignKey<T>>
{
  using type = T;
};

// Helper alias to get the referenced type
template <IsForeignKey T>
using ForeignKeyType = typename ForeignKeyTypeT<T>::type;

// --- Basic Type Concepts ---

template <typename T>
concept isIntegral = std::integral<T>;
template <typename T>
concept floatingPoint = std::floating_point<T>;
template <typename T>
concept isString = std::is_same_v<T, std::string>;
template <typename T>
concept isBlob = std::is_same_v<T, std::vector<uint8_t>>;

/*!
 * A type supported by the database is either:
 *  - A basic integral type
 *  - A floating point type
 *  - A string
 *  - A BLOB (binary data as std::vector<uint8_t>)
 *  - A single transfer object
 *  - Or a repeated field of transfer objects
 */
template <typename T>
concept isSupportedDBType = isIntegral<T> || floatingPoint<T> || isString<T> ||
                            isBlob<T> || ValidTransferObject<T>;


}  // namespace cpp_sqlite

#endif  // DB_TRAITS_HPP