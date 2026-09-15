
enable_testing()

find_package(GTest REQUIRED)
add_executable(cpp_sqlite_test 
    testDatabase.cpp
    testDatabase.hpp)
    
set_target_properties(cpp_sqlite_test PROPERTIES LINKER_LANGUAGE CXX)

target_link_libraries(cpp_sqlite_test 
    PUBLIC
        spdlog::spdlog
    PRIVATE
        cpp_sqlite
        GTest::GTest
        GTest::Main
        SQLite3::SQLite3
        boost::boost)

target_compile_features(cpp_sqlite_test PRIVATE cxx_std_20)

target_include_directories(cpp_sqlite_test PUBLIC
${GTEST_INCLUDE_DIRS}
$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}> 
$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../src> 
)