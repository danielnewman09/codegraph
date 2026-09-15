
target_sources(cpp_sqlite PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/DBDatabase.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/DBDataAccessObject.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/DBTransaction.cpp
)

# Note: target_include_directories is now handled by root CMakeLists.txt
# to support cpp_sqlite/src/... include paths