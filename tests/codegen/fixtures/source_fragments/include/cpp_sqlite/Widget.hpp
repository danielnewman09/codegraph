#ifndef CPP_SQLITE_WIDGET_HPP
#define CPP_SQLITE_WIDGET_HPP

#include <cstdint>
#include <string>

namespace cpp_sqlite
{
// A forward declaration kept out of the graph.
class Database;
/** Identifiers are plain 32-bit values. */
using WidgetId = std::uint32_t;
/** A documented widget. */
class Widget
{
public:
  /** The widget identifier. */
  WidgetId id() const;
  /** Assign the widget identifier. */
  void setId(WidgetId value);

private:
  WidgetId m_id;
  std::string m_name;
};
}  // namespace cpp_sqlite

#endif  // CPP_SQLITE_WIDGET_HPP
