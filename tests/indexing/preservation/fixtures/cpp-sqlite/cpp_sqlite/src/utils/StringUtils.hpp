#ifndef STRING_UTILS_HPP
#define STRING_UTILS_HPP

#include <string>
#include <string_view>

namespace cpp_sqlite
{

/*!
 * \brief Strip namespace prefix from a type name
 *
 * Converts "namespace::TypeName" to "TypeName"
 * Handles nested namespaces: "outer::inner::TypeName" -> "TypeName"
 * If no namespace exists, returns the original name unchanged
 *
 * \param fullTypeName The full type name (e.g., from boost::typeindex)
 * \return Type name without namespace prefix
 *
 * \example
 * stripNamespace("std::vector") -> "vector"
 * stripNamespace("my_ns::MyClass") -> "MyClass"
 * stripNamespace("MyClass") -> "MyClass"
 */
inline std::string stripNamespace(std::string_view fullTypeName)
{
  // Find the last occurrence of "::"
  auto pos = fullTypeName.rfind("::");

  if (pos == std::string_view::npos)
  {
    // No namespace found, return as-is
    return std::string(fullTypeName);
  }

  // Return everything after the last "::"
  return std::string(fullTypeName.substr(pos + 2));
}

}  // namespace cpp_sqlite

#endif  // STRING_UTILS_HPP
