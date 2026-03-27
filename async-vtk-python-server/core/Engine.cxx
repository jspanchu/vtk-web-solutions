#include "Engine.h"
#include <vtkDataObject.h>
#include <vtkObjectFactory.h>
#include <vtkPolyData.h>
#include <vtkPythonArgs.h>
#include <vtkPythonUtil.h>
#include <vtkUnstructuredGrid.h>
#include <vtkXMLPolyDataReader.h>
#include <vtkXMLUnstructuredGridReader.h>


#include <filesystem>
#include <iostream>

VTK_ABI_NAMESPACE_BEGIN

namespace
{
bool EnsureMainThread(const char* functionName, std::thread::id threadId)
{
  if (std::this_thread::get_id() != threadId)
  {
    std::string errorMessage =
      "Function " + std::string(functionName) + " called from wrong thread!";
    vtkPythonScopeGilEnsurer gilEnsurer;
    PyErr_SetString(PyExc_RuntimeError, errorMessage.c_str());
    return false;
  }
  return true;
}

const char* ASYNCIO_MODULE = "asyncio";
const char* ASYNCIO_METHOD_GET_RUNNING_LOOP = "get_running_loop";
const char* ASYNCIO_METHOD_CREATE_FUTURE = "create_future";
const char* ASYNCIO_METHOD_CALL_SOON_THREADSAFE = "call_soon_threadsafe";
const char* ASYNCIO_METHOD_FUTURE_SET_RESULT = "set_result";
const char* ENGINE_ON_DATA_LOADED_METHOD = "on_data_loaded";

} // namespace

vtkStandardNewMacro(Engine);

Engine::Engine()
  : AsyncioLoop(nullptr)
  , CallSoonThreadSafeFunction(nullptr)
  , OwnerThreadId(std::this_thread::get_id())
{
  this->IOTaskQueue = std::make_unique<vtkThreadedTaskQueue<void, const std::string&, PyObject*>>(
    [this](const std::string& file_name, PyObject* resultFuture)
    { this->LoadDataReal(file_name, resultFuture); }, false, /*buffer_size=*/-1);
}

Engine::~Engine() = default;

void Engine::PrintSelf(ostream& os, vtkIndent indent)
{
  this->Superclass::PrintSelf(os, indent);
}

PyObject* Engine::load_data(const std::string& file_name)
{
  vtkLogScopeFunction(INFO);
  if (!EnsureMainThread("Engine::load_data", this->OwnerThreadId))
  {
    return nullptr;
  }
  vtkPythonScopeGilEnsurer gilEnsurer;
  PyObject* future = this->CreateFuture();
  if (future)
  {
    Py_INCREF(future);
    this->IOTaskQueue->Push(file_name, std::move(future));
  }
  return future;
}

void Engine::on_data_loaded(vtkSmartPointer<vtkDataObject> outputData, PyObject* resultFuture)
{
  vtkLogScopeFunction(INFO);
  if (!EnsureMainThread("Engine::on_data_loaded", this->OwnerThreadId))
  {
    return;
  }
  vtkPythonScopeGilEnsurer gilEnsurer;
  vtkSmartPyObject outputDataPythonPtr;
  if (outputData != nullptr)
  {
    outputDataPythonPtr = vtkPythonUtil::FindObject(outputData);
  }

  this->SetFutureResult(resultFuture, outputDataPythonPtr);
}

PyObject* Engine::CreateFuture()
{
  vtkLogScopeFunction(INFO);
  if (!EnsureMainThread("Engine::CreateFuture", this->OwnerThreadId))
  {
    return nullptr;
  }
  vtkPythonScopeGilEnsurer gilEnsurer;
  if (this->AsyncioLoop == nullptr)
  {
    vtkSmartPyObject moduleName = PyUnicode_FromString(ASYNCIO_MODULE);
    vtkSmartPyObject asyncioModule = PyImport_GetModule(moduleName);
    if (!asyncioModule)
    {
      asyncioModule = PyImport_ImportModule(ASYNCIO_MODULE);
      if (!asyncioModule)
      {
        return nullptr; // Import failed, return nullptr
      }
    }
    // Get the asyncio event loop
    this->AsyncioLoop =
      PyObject_CallMethod(asyncioModule, ASYNCIO_METHOD_GET_RUNNING_LOOP, nullptr);
    if (!this->AsyncioLoop)
    {
      PyErr_SetString(PyExc_RuntimeError,
        "No running event loop found. Please run this code "
        "inside an async def function.");
      return nullptr;
    }
    // Get the call_soon_threadsafe method
    this->CallSoonThreadSafeFunction =
      PyObject_GetAttrString(this->AsyncioLoop, ASYNCIO_METHOD_CALL_SOON_THREADSAFE);
    if (!this->CallSoonThreadSafeFunction)
    {
      PyErr_SetString(
        PyExc_RuntimeError, "Failed to get call_soon_threadsafe method from asyncio loop.");
      return nullptr;
    }
  }
  // Create a future using the asyncio event loop
  PyObject* future = PyObject_CallMethod(this->AsyncioLoop, ASYNCIO_METHOD_CREATE_FUTURE, nullptr);
  if (!future)
  {
    vtkErrorMacro("Failed to create asyncio future.");
    return nullptr;
  }
  return future;
}

void Engine::SetFutureResult(PyObject* resultFuture, PyObject* value)
{
  vtkLogScopeFunction(INFO);
  vtkSmartPyObject setResultFunction =
    PyObject_GetAttrString(resultFuture, ASYNCIO_METHOD_FUTURE_SET_RESULT);
  if (PyObject_CallFunctionObjArgs(setResultFunction.GetPointer(), value, nullptr) == nullptr)
  {
    PyErr_Print();
    PyErr_Clear();
    vtkErrorMacro(<< "Failed to set result in future");
  }
}

void Engine::NotifyDataLoaded(vtkSmartPointer<vtkDataObject> outputData, PyObject* resultFuture)
{
  vtkLogScopeFunction(INFO);
  if (outputData)
  {
    vtkLog(INFO, << "Data loaded " << outputData->GetClassName());
  }
  else
  {
    vtkLog(INFO, << "Data load failed.");
  }
  // same as
  // ```python
  // loop.call_soon_threadsafe(engine.on_data_loaded, output_data, resultFuture)
  // ```
  vtkPythonScopeGilEnsurer gilEnsurer;
  vtkSmartPyObject selfPythonPtr = vtkPythonUtil::GetObjectFromPointer(this);
  vtkSmartPyObject outputDataPythonPtr = vtkPythonUtil::GetObjectFromPointer(outputData);
  vtkSmartPyObject onDataLoadedMethod =
    PyObject_GetAttrString(selfPythonPtr.GetPointer(), ENGINE_ON_DATA_LOADED_METHOD);
  // same as
  // ```python
  // engine.on_data_loaded(outputData, resultFuture)
  // ```
  // on the main thread
  PyObject_CallFunctionObjArgs(this->CallSoonThreadSafeFunction.GetPointer(),
    onDataLoadedMethod.GetPointer(), outputDataPythonPtr.GetPointer(), resultFuture, nullptr);
  // Only decrement the reference if this is a worker thread (i.e., not the main
  // thread)
  if (std::this_thread::get_id() != this->OwnerThreadId)
  {
    Py_DECREF(resultFuture);
  }
}

void Engine::LoadDataReal(const std::string& fileName, PyObject* resultFuture)
{
  vtkLogScopeFunction(INFO);
  std::filesystem::path filePath(fileName);
  vtkSmartPointer<vtkDataObject> outputData;
  if (filePath.extension() == ".vtu")
  {
    auto reader = vtkSmartPointer<vtkXMLUnstructuredGridReader>::New();
    reader->SetFileName(fileName.c_str());
    reader->Update();
    outputData = reader->GetOutput();
  }
  else if (filePath.extension() == ".vtp")
  {
    auto reader = vtkSmartPointer<vtkXMLPolyDataReader>::New();
    reader->SetFileName(fileName.c_str());
    reader->Update();
    outputData = reader->GetOutput();
  }
  else
  {
    vtkErrorMacro(<< "No suitable reader found for grid file format: " << fileName);
  }
  this->NotifyDataLoaded(outputData, resultFuture);
}

VTK_ABI_NAMESPACE_END
