#pragma once

#include "asyncDemoCoreModule.h"

#include <vtkObject.h>
#include <vtkSmartPyObject.h>
#include <vtkThreadedTaskQueue.h>

#include <memory>
#include <string>
#include <thread>

VTK_ABI_NAMESPACE_BEGIN
class vtkDataObject;

class ASYNCDEMOCORE_EXPORT Engine : public vtkObject
{
public:
  static Engine* New();
  vtkTypeMacro(Engine, vtkObject);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  /**
   * @brief Loads data from a file.
   * @param file_name The name of the file to load.
   */
  PyObject* load_data(const std::string& file_name);

  /**
   * @brief Called when data has been loaded.
   * @param outputData The data that was loaded.
   * @param resultFuture The future object to set the result on.
   */
  void on_data_loaded(vtkSmartPointer<vtkDataObject> outputData, PyObject* resultFuture);

protected:
  Engine();
  ~Engine() override;

private:
  Engine(const Engine&) = delete;
  void operator=(const Engine&) = delete;

  vtkSmartPyObject AsyncioLoop;
  vtkSmartPyObject CallSoonThreadSafeFunction;
  std::thread::id OwnerThreadId;
  std::unique_ptr<vtkThreadedTaskQueue<void, const std::string&, PyObject*>> IOTaskQueue;

  PyObject* CreateFuture();
  void SetFutureResult(PyObject* resultFuture, PyObject* value);

  void NotifyDataLoaded(vtkSmartPointer<vtkDataObject> outputData, PyObject* resultFuture);

  void LoadDataReal(const std::string& file_name, PyObject* resultFuture);
};
VTK_ABI_NAMESPACE_END
