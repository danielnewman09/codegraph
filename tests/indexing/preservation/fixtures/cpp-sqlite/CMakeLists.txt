cmake_minimum_required(VERSION 3.15)

set(PROJECT_NAME cpp_sqlite)

project(${PROJECT_NAME} VERSION 0.1.0 LANGUAGES C CXX)

# Set compiler options
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_compile_options(-Wall -Wextra -Wpedantic)

add_library(${PROJECT_NAME})
set_target_properties(${PROJECT_NAME} PROPERTIES LINKER_LANGUAGE CXX)

target_link_libraries(${PROJECT_NAME} 
        PUBLIC 
                spdlog::spdlog
                boost::boost
                SQLite3::SQLite3
                )

# Add all relevant include directories
# For build: include from project root to allow cpp_sqlite/src/... paths
# For install: include from install root to allow cpp_sqlite/src/... paths
target_include_directories(${PROJECT_NAME} PUBLIC
$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
$<INSTALL_INTERFACE:include>
)

# Find the packages (dependencies) provided by Conan
find_package(SQLite3 REQUIRED CONFIG)
find_package(Boost REQUIRED)
find_package(spdlog REQUIRED)

# Enable testing at the top level
enable_testing()

# IMPORTANT: Test framework now available before adding source directories
add_subdirectory(cpp_sqlite)

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)


# Installation rules
install(TARGETS ${PROJECT_NAME}
        EXPORT ${PROJECT_NAME}Targets
        RUNTIME DESTINATION bin
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        INCLUDES DESTINATION include
        )

# Install all header files maintaining directory structure
# This creates: include/cpp_sqlite/src/cpp_sqlite/*.hpp
#               include/cpp_sqlite/src/utils/*.hpp
# Allowing includes like: #include "cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp"
install(DIRECTORY cpp_sqlite/
        DESTINATION include/${PROJECT_NAME}
        FILES_MATCHING PATTERN "*.hpp"
        PATTERN "*.cpp" EXCLUDE
        PATTERN "test" EXCLUDE)

# Create and install package config files
include(CMakePackageConfigHelpers)

# Generate the config file that includes the exports
configure_package_config_file(
        ${CMAKE_CURRENT_SOURCE_DIR}/Config.cmake.in
        ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}Config.cmake
        INSTALL_DESTINATION lib/cmake/${PROJECT_NAME}
)

# Generate version file
write_basic_package_version_file(
        ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}ConfigVersion.cmake
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion
)

# Install the configuration files
install(FILES
        ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}Config.cmake
        ${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}ConfigVersion.cmake
        DESTINATION lib/cmake/${PROJECT_NAME}
)

# Install the targets file
install(EXPORT ${PROJECT_NAME}Targets
        FILE ${PROJECT_NAME}Targets.cmake
        NAMESPACE ${PROJECT_NAME}::
        DESTINATION lib/cmake/${PROJECT_NAME})        