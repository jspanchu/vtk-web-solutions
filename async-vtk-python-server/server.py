import asyncio
import functools
import os

from asyncdemo.asyncDemoCore import Engine

from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkDataSetMapper,
    vtkRenderWindow,
    vtkRenderer,
    vtkRenderWindowInteractor,
)
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleSwitch  # noqa
import vtkmodules.vtkRenderingOpenGL2  # noqa
import vtkmodules.vtkIOXML  # noqa

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageWithDrawerLayout 
from trame.widgets import vuetify3, vtk
from trame.decorators import TrameApp, change, trigger


@TrameApp()
class FileBrowserDemo:
    def __init__(self):
        self.server = get_server()
        self.server.cli.add_argument("--working-dir", "-w", help="Initial working directory for file browser", default=os.path.expanduser("~"))
        self.state = self.server.state
        self.ctrl = self.server.controller
        self.engine = Engine()

        self.setup_vtk()
        self.setup_ui()

        args = self.server.cli.parse_known_args()[0]
        # Initialize file browser state
        start_dir = args.working_dir
        self.state.browse_dialog = False
        self.state.browse_current_dir = start_dir
        self.state.browse_items = []
        self.state.browse_selected_files = []
        self.state.browse_search = ""
        self.state.loaded_files = []
        self._refresh_browse_items(start_dir)
        self.pending_tasks = set()
        self.actors = []
        self._last_clicked_path = None

    def setup_vtk(self):
        self.renderer = vtkRenderer(background=(0.2, 0.2, 0.2))
        self.render_window = vtkRenderWindow()
        self.render_window.AddRenderer(self.renderer)
        self.render_window.OffScreenRenderingOn()

        interactor = vtkRenderWindowInteractor()
        interactor.SetRenderWindow(self.render_window)
        interactor.GetInteractorStyle().SetCurrentStyleToTrackballCamera()

        self.render_window.Render()

    def setup_ui(self):
        with SinglePageWithDrawerLayout(self.server) as layout:
            layout.title.set_text("Async VTK File Browser Demo")

            with layout.toolbar:
                vuetify3.VSpacer()
                vuetify3.VBtn(
                    icon="mdi-camera-flip",
                    variant="text",
                    click=self.reset_camera,
                )
                vuetify3.VBtn(
                    icon="mdi-delete",
                    variant="text",
                    click=self.remove_all_actors,
                )

            with layout.drawer:
                with vuetify3.VCardTitle(classes="d-flex align-center"):
                    vuetify3.VIcon("mdi-database", classes="mr-2")
                    html_text = "Datasets"
                    vuetify3.VCardTitle(html_text)
                    vuetify3.VSpacer()
                    vuetify3.VBtn(
                        icon="mdi-plus",
                        variant="text",
                        click=self.open_file_browser,
                    )
                vuetify3.VDivider()
                with vuetify3.VList(density="compact"):
                    with vuetify3.VListItem(
                        v_for="(item, i) in loaded_files",
                        key="i",
                        title=("item.name",),
                    ):
                        with vuetify3.Template(v_slot_prepend=True):
                            vuetify3.VProgressCircular(
                                v_if="item.loading",
                                indeterminate=True,
                                size=20,
                                width=2,
                                classes="mr-1",
                            )
                            vuetify3.VBtn(
                                v_else=True,
                                icon=("item.visible ? 'mdi-eye' : 'mdi-eye-off'",),
                                variant="text",
                                density="compact",
                                size="small",
                                click=(self.toggle_visibility, "[i]"),
                            )
                            vuetify3.VBtn(
                                icon="mdi-delete",
                                variant="text",
                                click=(self.remove_actor, "[i]"),
                            )

            with layout.content:
                with vuetify3.VContainer(fluid=True, classes="fill-height pa-0 ma-0"):
                    with vtk.VtkRemoteView(self.render_window) as view:
                        self.ctrl.view_update = view.update
                        self.ctrl.view_reset_camera = view.reset_camera

            # --- File Browser Dialog ---
            with vuetify3.VDialog(v_model=("browse_dialog",), max_width="700"):
                with vuetify3.VCard():
                    vuetify3.VCardTitle("Browse for VTP / VTU file")
                    with vuetify3.VCardText():
                        with vuetify3.VRow(align="center", classes="mb-2", no_gutters=True):
                            vuetify3.VBtn(
                                icon="mdi-arrow-up",
                                variant="text",
                                density="comfortable",
                                click=self.browse_go_up,
                            )
                            with vuetify3.VCol(classes="pl-2"):
                                vuetify3.VTextField(
                                    v_model=("browse_current_dir",),
                                    label="Path (directory or file)",
                                    variant="outlined",
                                    density="compact",
                                    hide_details=True,
                                    keyup_enter=self.navigate_to_typed_path,
                                )
                            vuetify3.VBtn(
                                icon="mdi-arrow-right",
                                variant="text",
                                density="comfortable",
                                click=self.navigate_to_typed_path,
                            )
                        vuetify3.VTextField(
                            v_model=("browse_search",),
                            label="Filter by name",
                            prepend_inner_icon="mdi-magnify",
                            variant="outlined",
                            density="compact",
                            hide_details=True,
                            clearable=True,
                            classes="mb-2",
                        )
                        with vuetify3.VList(
                            density="compact",
                            style="max-height: 400px; overflow-y: auto;",
                        ):
                            with vuetify3.VListItem(
                                v_for="(entry, idx) in browse_items.filter(e => !browse_search || e.name.toLowerCase().includes((browse_search || '').toLowerCase()))",
                                key="idx",
                                title=("entry.name",),
                                prepend_icon=("entry.is_dir ? 'mdi-folder' : 'mdi-file'",),
                                click=(self.browse_item_clicked, "[$event.ctrlKey, $event.shiftKey, entry]"),
                                active=("browse_selected_files.includes(entry.path)",),
                                color="primary",
                                style="user-select: none;",
                            ):
                                pass
                    with vuetify3.VCardActions():
                        vuetify3.VSpacer()
                        vuetify3.VBtn(
                            "Open",
                            prepend_icon="mdi-file-download",
                            variant="tonal",
                            color="primary",
                            click=self.open_selected_file,
                        )
                        vuetify3.VBtn("Close", variant="text", click=self.close_file_browser)

    # --- File browser helpers ---

    def _refresh_browse_items(self, directory):
        """Scan directory and update state with entries (dirs first, then .vtp/.vtu files)."""
        items = []
        try:
            for entry in sorted(os.scandir(directory), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.is_dir():
                    items.append({"name": entry.name, "is_dir": True, "path": entry.path})
                elif entry.name.lower().endswith((".vtp", ".vtu")):
                    items.append({"name": entry.name, "is_dir": False, "path": entry.path})
        except PermissionError:
            pass
        self.state.browse_items = items

    @trigger("open_file_browser")
    def open_file_browser(self):
        self.state.browse_search = ""
        self._refresh_browse_items(self.state.browse_current_dir)
        self.state.browse_dialog = True

    @trigger("close_file_browser")
    def close_file_browser(self):
        self.state.browse_dialog = False

    @trigger("browse_go_up")
    def browse_go_up(self):
        parent = os.path.dirname(self.state.browse_current_dir)
        if parent and parent != self.state.browse_current_dir:
            self.state.browse_current_dir = parent
            self._refresh_browse_items(parent)

    @trigger("navigate_to_typed_path")
    def navigate_to_typed_path(self):
        target = self.state.browse_current_dir
        if os.path.isfile(target) and target.lower().endswith((".vtp", ".vtu")):
            self.state.browse_selected_files = [target]
        elif os.path.isdir(target):
            self.state.browse_selected_files = []
            self._refresh_browse_items(target)

    @trigger("open_typed_file")
    def open_typed_file(self):
        target = self.state.browse_current_dir
        if os.path.isfile(target) and target.lower().endswith((".vtp", ".vtu")):
            self._start_load(target)

    @trigger("open_selected_file")
    def open_selected_file(self):
        selected = list(self.state.browse_selected_files)
        for path in selected:
            if os.path.isfile(path) and path.lower().endswith((".vtp", ".vtu")):
                self._start_load(path)
        self.state.browse_selected_files = []

    def _start_load(self, file_path):
        # Add a placeholder entry immediately so the spinner shows up
        index = len(self.state.loaded_files)
        self.actors.append(None)
        with self.state:
            loaded_files = list(self.state.loaded_files)
            loaded_files.append({"name": os.path.basename(file_path), "visible": True, "loading": True})
            self.state.loaded_files = loaded_files

        task = asyncio.create_task(self._load_file(file_path))
        task.add_done_callback(functools.partial(self._on_load_done, file_path=file_path, index=index))
        self.pending_tasks.add(task)

    @trigger("browse_item_clicked")
    def browse_item_clicked(self, ctrl_key, shift_key, entry):
        path = entry["path"]
        if entry["is_dir"]:
            self.state.browse_current_dir = path
            self.state.browse_selected_files = []
            self.state.browse_search = ""
            self._refresh_browse_items(path)
        else:
            selected = list(self.state.browse_selected_files)
            if shift_key and self._last_clicked_path:
                # Range selection: select all files between last click and current
                file_items = [e for e in self.state.browse_items if not e["is_dir"]]
                paths = [e["path"] for e in file_items]
                try:
                    start = paths.index(self._last_clicked_path)
                    end = paths.index(path)
                    if start > end:
                        start, end = end, start
                    range_paths = paths[start:end + 1]
                    # Union with existing selection
                    for p in range_paths:
                        if p not in selected:
                            selected.append(p)
                except ValueError:
                    selected = [path]
            elif ctrl_key:
                # Toggle individual selection
                if path in selected:
                    selected.remove(path)
                else:
                    selected.append(path)
            else:
                # Plain click: single selection
                selected = [path]
            self._last_clicked_path = path
            self.state.browse_selected_files = selected

    async def _load_file(self, file_path):
        """Await the future returned by engine.load_data."""
        return await self.engine.load_data(file_path)

    def _on_load_done(self, task, file_path, index):
        """Callback to handle results from engine.load_data."""
        self.pending_tasks.discard(task)
        try:
            output_data = task.result()
            if output_data is not None:
                mapper = vtkDataSetMapper(input_data=output_data)
                actor = vtkActor()
                actor.SetMapper(mapper)
                self.renderer.AddActor(actor)
                self.actors[index] = actor
                # Mark loading complete
                with self.state:
                    loaded_files = list(self.state.loaded_files)
                    loaded_files[index] = {**loaded_files[index], "loading": False}
                    self.state.loaded_files = loaded_files
                self.ctrl.view_reset_camera()
                self.ctrl.view_update()
            else:
                print(f"Failed to load dataset: {file_path}")
                with self.state:
                    loaded_files = list(self.state.loaded_files)
                    loaded_files[index] = {**loaded_files[index], "name": loaded_files[index]["name"] + " (failed)", "loading": False, "visible": False}
                    self.state.loaded_files = loaded_files
        except Exception as e:
            print(f"Error loading dataset: {e}")
            with self.state:
                loaded_files = list(self.state.loaded_files)
                loaded_files[index] = {**loaded_files[index], "name": loaded_files[index]["name"] + " (error)", "loading": False, "visible": False}
                self.state.loaded_files = loaded_files

    @trigger("toggle_visibility")
    def toggle_visibility(self, index):
        actor = self.actors[index]
        if actor is None:
            return
        visible = not actor.GetVisibility()
        actor.SetVisibility(visible)
        self.render_window.Render()

        with self.state:
            loaded_files = list(self.state.loaded_files)
            loaded_files[index] = {**loaded_files[index], "visible": visible}
            self.state.loaded_files = loaded_files
        self.reset_camera()

    @trigger("remove_actor")
    def remove_actor(self, index):
        actor = self.actors[index]
        if actor is not None:
            self.renderer.RemoveViewProp(actor)
            self.actors[index] = None
            self.render_window.Render()

        with self.state:
            loaded_files = list(self.state.loaded_files)
            del loaded_files[index]
            self.state.loaded_files = loaded_files
        self.reset_camera()

    @trigger("reset_camera")
    def reset_camera(self):
        self.ctrl.view_reset_camera()
        self.ctrl.view_update()

    @trigger("remove_all_actors")
    def remove_all_actors(self):
        self.renderer.RemoveAllViewProps()
        self.actors.clear()
        self.render_window.Render()
        with self.state:
            self.state.loaded_files = []
        self.reset_camera()

if __name__ == "__main__":
    app = FileBrowserDemo()
    app.server.start()
