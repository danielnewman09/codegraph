#include "cpp_sqlite/Widget.hpp"

namespace cpp_sqlite
{

WidgetId Widget::id() const { return m_id; }

void Widget::setId(WidgetId value) { m_id = value; }

}  // namespace cpp_sqlite
