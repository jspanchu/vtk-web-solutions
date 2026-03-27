cmake_minimum_required(VERSION 3.31)
project(AsyncDemo VERSION 0.0.1 LANGUAGES CXX)
option(BUILD_SHARED_LIBS "Build shared libraries" ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
include(GNUInstallDirs)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin" CACHE PATH "Single output directory for building all executables." FORCE)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib" CACHE PATH "Single output directory for building all libraries." FORCE)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib" CACHE PATH "Single output directory for building all archives." FORCE)
if(CMAKE_BUILD_TYPE MATCHES "Debug" AND CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
  option(ASYNC_DEMO_WINDOWS_PYTHON_DEBUGGABLE ON BOOL "Build against debuggable Python support on Windows")
  option(ASYNC_DEMO_WINDOWS_PYTHON_DEBUGGABLE_REPLACE_SUFFIX ON)
endif()
find_package(VTK CONFIG REQUIRED COMPONENTS CommonCore Python)
set(CMAKE_INSTALL_LIBDIR ".")
set(_vtk_module_library_destination "${CMAKE_INSTALL_LIBDIR}/asyncdemo")
set(_vtk_module_module_destination "${CMAKE_INSTALL_LIBDIR}")
set(_vtk_module_runtime_destination "${CMAKE_INSTALL_BINDIR}")
if (WIN32)
  # Ensure the dlls end up in lib/vtkmodules as well
  set(_vtk_module_runtime_destination "${CMAKE_INSTALL_LIBDIR}/asyncdemo")
elseif(APPLE)
  # These rpaths are required, always add them
  set(CMAKE_MACOSX_RPATH ON)
  list(APPEND CMAKE_INSTALL_RPATH "@loader_path" "@loader_path/../vtkmodules" "@loader_path/../vtkmodules/.dylibs")
else() # assumes Linux + GNU-based toolchain
  # required as the VTK wheels are build with the C++98 ABI
  list(APPEND CMAKE_CXX_FLAGS "-D_GLIBCXX_USE_CXX11_ABI=0")
  # These two rpaths are required, always add them
  list(APPEND CMAKE_INSTALL_RPATH "$ORIGIN" "$ORIGIN/../vtkmodules")
endif ()
set(requested_modules)
list(APPEND requested_modules "AsyncDemo::Core")
set(asyncdemo_export asyncdemo)
vtk_module_scan(
  MODULE_FILES     "${CMAKE_CURRENT_SOURCE_DIR}/core/vtk.module"
  REQUEST_MODULES  ${requested_modules}
  PROVIDES_MODULES asyncdemo_modules
  ENABLE_TESTS     OFF)
# Build the module
vtk_module_build(
  MODULES ${asyncdemo_modules}
  PACKAGE ${PROJECT_NAME}
  INSTALL_EXPORT ${asyncdemo_export}
  ARCHIVE_DESTINATION   "${CMAKE_INSTALL_LIBDIR}/asyncdemo"
  HEADERS_DESTINATION   "${CMAKE_INSTALL_LIBDIR}/asyncdemo/include/asyncdemo-${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}"
  CMAKE_DESTINATION     "${CMAKE_INSTALL_LIBDIR}/asyncdemo/cmake/asyncdemo"
  LICENSE_DESTINATION   "${CMAKE_INSTALL_LIBDIR}/asyncdemo"
  HIERARCHY_DESTINATION "${CMAKE_INSTALL_LIBDIR}/asyncdemo/hierarchy/${CMAKE_PROJECT_NAME}"
  RUNTIME_DESTINATION   "${_vtk_module_runtime_destination}"
  LIBRARY_DESTINATION   "${_vtk_module_library_destination}"
  VERSION             ${PROJECT_VERSION}
  SOVERSION           "1")
# Wrap the module for Python
vtk_module_wrap_python(
  MODULES         ${asyncdemo_modules}
  WRAPPED_MODULES asyncdemo_wrapped_modules
  INSTALL_EXPORT  ${asyncdemo_export}
  PYTHON_PACKAGE  "asyncdemo"
  CMAKE_DESTINATION   "${CMAKE_INSTALL_LIBDIR}/cmake/asyncdemo"
  MODULE_DESTINATION  "${_vtk_module_module_destination}"
  LIBRARY_DESTINATION "${CMAKE_INSTALL_LIBDIR}"
  USE_DEBUG_SUFFIX    "${ASYNC_DEMO_WINDOWS_PYTHON_DEBUGGABLE}"
  REPLACE_DEBUG_SUFFIX "${ASYNC_DEMO_WINDOWS_PYTHON_DEBUGGABLE_REPLACE_SUFFIX}"
  # Static Python modules are almost never wanted.
  BUILD_STATIC    OFF
  SOABI               "${Python${VTK_PYTHON_VERSION}_SOABI}"
  INSTALL_HEADERS OFF)
set(python_modules "")
set(python_module_imports "")
foreach(module IN LISTS asyncdemo_wrapped_modules)
  _vtk_module_get_module_property("${module}"
    PROPERTY  "library_name"
    VARIABLE  library_name)
  list(APPEND python_modules "'${library_name}'")
  list(APPEND python_module_imports "from .${library_name} import *")
endforeach()
list(JOIN python_modules ,  python_modules_string)
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/python/__init__.py.in"
  "${CMAKE_BINARY_DIR}/asyncdemo/__init__.py"
  @ONLY)
# Install the Python package
install(
  DIRECTORY
    "${CMAKE_BINARY_DIR}/asyncdemo"
  DESTINATION "${_vtk_module_module_destination}")
