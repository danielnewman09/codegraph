from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps
from conan.tools.files import copy
import os

class CppSQLite(ConanFile):
    name = "cpp_sqlite"
    version = "0.1.0"
    license = "MIT"
    author = "Daniel Newman"
    url = "https://github.com/danielnewman/cpp-sqlite"
    description = "A modern C++20 SQLite wrapper using Boost.Describe for reflection"
    topics = ("sqlite", "database", "cpp20", "boost")

    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False], "build_testing": [True, False]}
    default_options = {"shared": False, "fPIC": True, "build_testing": False}

    # Sources are located in the same place as this recipe, copy them to the recipe
    # Include source files for debugging support
    exports_sources = "CMakeLists.txt", "Config.cmake.in", "cpp_sqlite/*"

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC


    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")

        # Configure Boost options to minimize build
        self.options["boost/*"].without_wave = True
        self.options["boost/*"].without_type_erasure = True
        self.options["boost/*"].without_process = True
        self.options["boost/*"].without_nowide = True
        self.options["boost/*"].without_log = True
        self.options["boost/*"].without_locale = True
        self.options["boost/*"].without_fiber = True
        self.options["boost/*"].without_coroutine = True
        self.options["boost/*"].without_contract = True
        self.options["boost/*"].without_cobalt = True
        self.options["boost/*"].without_atomic = True
        self.options["boost/*"].without_chrono = True
        self.options["boost/*"].without_container = False
        self.options["boost/*"].without_filesystem = True
        self.options["boost/*"].without_system = False
        self.options["boost/*"].without_thread = True
        self.options["boost/*"].without_test = True

        # Disable problematic Boost components for Emscripten
        if self.settings.os == "Emscripten":
            self.options["boost/*"].without_stacktrace = True
            self.options["boost/*"].without_context = True
            self.options["boost/*"].without_iostreams = True


    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_CXX_STANDARD"] = "20"
        tc.cache_variables["CMAKE_CXX_STANDARD_REQUIRED"] = "ON"

        # Workaround for fmt/spdlog consteval issue
        # See: https://github.com/emscripten-core/emscripten/issues/22795
        # Disable compile-time format string checking
        tc.cache_variables["CMAKE_CXX_FLAGS"] = "-DFMT_USE_CONSTEVAL=0 -DFMT_CONSTEVAL="

        # Disable tests for Emscripten
        if self.settings.os == "Emscripten":
            tc.cache_variables["BUILD_TESTING"] = "OFF"

        # Note: Don't set output directories - let CMakeLists.txt handle it
        # The ${CMAKE_BINARY_DIR} variable isn't properly expanded in cache_variables

        # Ensure CMake can find Conan-generated dependency configs
        # This is needed when using external toolchain files (e.g., Emscripten)
        # cmake_layout puts generators at {source}/build/{build_type}/generators
        generators_dir = os.path.join(self.source_folder, "build",
                                      str(self.settings.build_type), "generators")
        # Use both cache variable AND direct variable setting
        tc.cache_variables["CMAKE_PREFIX_PATH"] = generators_dir
        # Also set package _DIR directly in case CMAKE_PREFIX_PATH isn't searched first
        tc.cache_variables["SQLite3_DIR"] = generators_dir
        tc.cache_variables["spdlog_DIR"] = generators_dir
        tc.cache_variables["Boost_DIR"] = generators_dir
        tc.cache_variables["fmt_DIR"] = generators_dir  # Required by spdlog

        if self.options.build_testing:
            tc.variables["BUILD_TESTING"] = "ON"

        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        cmake = CMake(self)
        cmake.install()

        # Note: cmake.install() handles all header installation via CMakeLists.txt
        # Headers are installed to: include/cpp_sqlite/src/cpp_sqlite/*.hpp
        #                           include/cpp_sqlite/src/utils/*.hpp

        # Copy source files for debugging support (allows stepping into library code)
        copy(self, "*.cpp",
             src=os.path.join(self.source_folder, "cpp_sqlite", "src"),
             dst=os.path.join(self.package_folder, "src"),
             keep_path=True)

    def requirements(self):
        # Regular dependency for the library/app
        self.requires('sqlite3/3.47.0-local')
        self.requires("boost/1.86.0")
        self.requires('spdlog/1.14.1')
        # Test-only dependency
        self.test_requires("gtest/1.14.0")

    def build_requirements(self):
        self.tool_requires("cmake/3.22.6")

    def layout(self):
        cmake_layout(self)

    def package_info(self):
        self.cpp_info.libs = ["cpp_sqlite"]
        self.cpp_info.includedirs = ["include"]

        # Set C++ standard requirement
        self.cpp_info.cxxflags = ["-std=c++20"]

        # Propagate dependencies
        self.cpp_info.requires = ["sqlite3::sqlite3", "boost::boost", "spdlog::spdlog"]