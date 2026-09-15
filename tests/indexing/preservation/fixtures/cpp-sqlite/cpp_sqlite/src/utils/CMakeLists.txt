
target_sources(cpp_sqlite PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/Logger.cpp
)

# Note: target_include_directories is now handled by root CMakeLists.txt
# to support cpp_sqlite/src/... include paths