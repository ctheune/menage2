document.addEventListener("keydown", function (e) {
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;

  if (e.key === "Escape") {
    var pane = document.getElementById("details-pane");
    if (
      pane &&
      !pane.classList.contains("d-none") &&
      !document.getElementById("protocol-run")
    ) {
      e.preventDefault();
      document
        .querySelectorAll("input.todo-checkbox:checked")
        .forEach(function (cb) {
          cb.checked = false;
        });
      closeDetailsPane();
      return;
    }
  }

  // [ / ] / u are wired via hyperscript on the batch form in list_todos.pt.
  // c / P / h / a are wired via hyperscript on the batch-menu buttons there.
  // d / f / s / ~ / @ / l field shortcuts are wired via hyperscript in
  // _todo_details_panel.pt.
  // The repetition history panel is pure htmx: see the .todo-recurrence button
  // in _todo_groups.pt and _recurrence_history.pt.
});

// --- Details pane -----------------------------------------------------------

// Closing the details pane. Still reached from the Escape handlers below;
// the button that used to call it is hyperscript now.
function closeDetailsPane() {
  var pane = document.getElementById("details-pane");
  var panel = document.getElementById("details-panel");
  if (pane) pane.classList.add("d-none");
  if (panel) panel.innerHTML = "";
}

// --- Protocol run page interactions ----------------------------------------
//
// The run-item actions (done / send / edit) are plain htmx on the buttons in
// _protocol_run_partial.pt: done and send post and swap the whole section, and
// edit reveals that row's inline form via hyperscript. Only the j/k cursor and
// the hotkeys that click those buttons live here.

// --- Run-item navigation + hotkeys ---
var _runCurrentIdx = 0;

function _runItems() {
  return Array.from(document.querySelectorAll(".protocol-run-item"));
}
function _runHighlight() {
  var items = _runItems();
  items.forEach(function (el, i) {
    el.classList.toggle("is-current", i === _runCurrentIdx);
  });
  var current = items[_runCurrentIdx];
  if (current) current.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function _runMove(delta) {
  var items = _runItems();
  if (!items.length) return;
  _runCurrentIdx = Math.max(
    0,
    Math.min(items.length - 1, _runCurrentIdx + delta),
  );
  _runHighlight();
}
function _runFire(action) {
  var items = _runItems();
  var current = items[_runCurrentIdx];
  if (!current) return;
  var btn = current.querySelector(
    '.protocol-run-action[data-action="' + action + '"]',
  );
  if (btn) btn.click();
}

document.addEventListener("keydown", function (e) {
  if (!document.getElementById("protocol-run")) return;
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;
  if (e.key === "j" || e.key === "ArrowDown") {
    e.preventDefault();
    _runMove(1);
  } else if (e.key === "k" || e.key === "ArrowUp") {
    e.preventDefault();
    _runMove(-1);
  } else if (e.key === "c") {
    e.preventDefault();
    _runFire("done");
  } else if (e.key === "t") {
    e.preventDefault();
    _runFire("send");
  } else if (e.key === "e") {
    e.preventDefault();
    _runFire("edit");
  } else if (e.key === "Escape") {
    e.preventDefault();
    var pane = document.getElementById("details-pane");
    if (pane && !pane.classList.contains("d-none")) {
      document
        .querySelectorAll("input.todo-checkbox:checked")
        .forEach(function (cb) {
          cb.checked = false;
        });
      closeDetailsPane();
    } else {
      var run = document.getElementById("protocol-run");
      if (run && run.dataset.todoRoute) location.href = run.dataset.todoRoute;
    }
  }
});


// --- Bootstrapping ----------------------------------------------------------
//
// Protocol titles and items are edited with plain inputs and a view/edit
// toggle written in hyperscript (protocols/edit.pt, _protocol_item.pt), so
// there is nothing left to initialise for them here.

htmx.onLoad(function () {
  if (document.getElementById("protocol-run")) _runHighlight();
});
if (document.getElementById("protocol-run")) _runHighlight();

function isCaretAtStart(element) {
  // Works only in contentEditable with plaintext-only
  const selection = window.getSelection();
  if (!selection.rangeCount) return false;

  const range = selection.getRangeAt(0);
  return range.collapsed && range.startOffset === 0;
}
