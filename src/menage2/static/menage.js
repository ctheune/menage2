function initSortables(content) {
  var sortables = content.querySelectorAll(".sortable");
  for (var i = 0; i < sortables.length; i++) {
    var sortable = sortables[i];
    new Sortable(sortable, {
      animation: 150,
      filter: ".non-sortable", // 'filtered' class is not draggable
      ghostClass: "bg-blue-200",
    });
  }
}

// Full-screen image modal with prev/next navigation
var _modalImages = [];
var _modalIndex = 0;

function _modalUpdate() {
  var entry = _modalImages[_modalIndex];
  var img = document.getElementById("attachmentModalImage");
  if (img) {
    img.src = entry.full;
    img.alt = entry.alt;
  }
  var counter = document.getElementById("attachmentModalCounter");
  if (counter)
    counter.textContent =
      _modalImages.length > 1
        ? _modalIndex + 1 + " / " + _modalImages.length
        : "";
  var multi = _modalImages.length > 1;
  var prev = document.getElementById("attachmentModalPrev");
  var next = document.getElementById("attachmentModalNext");
  if (prev) prev.style.visibility = multi ? "visible" : "hidden";
  if (next) next.style.visibility = multi ? "visible" : "hidden";
}

function _modalNav(delta) {
  if (!_modalImages.length) return;
  _modalIndex =
    (_modalIndex + delta + _modalImages.length) % _modalImages.length;
  _modalUpdate();
}

document.addEventListener("click", function (e) {
  if (e.target.closest("#attachmentModalPrev")) {
    _modalNav(-1);
    return;
  }
  if (e.target.closest("#attachmentModalNext")) {
    _modalNav(1);
    return;
  }

  var thumb = e.target.closest(".todo-attachment-thumb");
  if (!thumb) return;
  e.stopPropagation();
  if (!thumb.dataset.fullUrl) return;
  var todoItem = thumb.closest(".todo-item");
  var all = todoItem
    ? Array.from(todoItem.querySelectorAll(".todo-attachment-thumb"))
    : [thumb];
  _modalImages = all.map(function (t) {
    return { full: t.dataset.fullUrl, alt: t.alt || "" };
  });
  _modalIndex = all.indexOf(thumb);
  if (_modalIndex < 0) _modalIndex = 0;
  _modalUpdate();
  var modalEl = document.getElementById("attachmentModal");
  if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
});

document.addEventListener("keydown", function (e) {
  var modal = document.getElementById("attachmentModal");
  if (!modal || !modal.classList.contains("show")) return;
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    _modalNav(-1);
  }
  if (e.key === "ArrowRight") {
    e.preventDefault();
    _modalNav(1);
  }
});

// Upload attachments to a todo
function uploadAttachments(files, todoId) {
  if (!files || files.length === 0) return;

  var formData = new FormData();
  for (var i = 0; i < files.length; i++) {
    formData.append("files[]", files[i]);
  }

  return fetch("/todos/" + todoId + "/attachments", {
    method: "POST",
    body: formData,
    headers: { "X-Requested-With": "XMLHttpRequest" },
  }).then(function (r) {
    if (!r.ok)
      return r.text().then(function (msg) {
        throw new Error(msg || "Upload failed");
      });
    return r;
  });
}

document.body.addEventListener("showValidationError", function (e) {
  var existing = document.getElementById("error-toast");
  if (existing) existing.remove();

  var toast = document.createElement("div");
  toast.id = "error-toast";
  toast.style.cssText =
    "position:fixed;bottom:1.5rem;left:1.5rem;z-index:9999;background:#dc2626;color:#fff;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.45);pointer-events:none;font-weight:600;";
  toast.textContent = (e.detail && e.detail.message) || "Validation error.";
  document.body.appendChild(toast);
  setTimeout(function () {
    toast.remove();
  }, 5000);
});

// Show error toast when todo text is empty (only tags entered)
document.body.addEventListener("showAddTodoError", function (e) {
  var existing = document.getElementById("error-toast");
  if (existing) existing.remove();

  var toast = document.createElement("div");
  toast.id = "error-toast";
  toast.style.cssText =
    "position:fixed;bottom:1.5rem;left:1.5rem;z-index:9999;background:#dc2626;color:#fff;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.45);pointer-events:none;font-weight:600;";
  toast.textContent = "A todo needs text, not just tags.";
  document.body.appendChild(toast);
  setTimeout(function () {
    toast.remove();
  }, 5000);
});

var _undoTimer = null;
// Either path that requests an undo (toast click or 'u' shortcut) cancels the
// auto-dismiss timer so the toast stays put until showUndoConfirm replaces it.
document.body.addEventListener("undoRequested", function () {
  clearTimeout(_undoTimer);
});

// Show undo toast when server fires showUndoToast HX-Trigger event
document.body.addEventListener("showUndoToast", function (e) {
  var existing = document.getElementById("undo-toast");
  if (existing) existing.remove();
  clearTimeout(_undoTimer);

  var toast = document.createElement("div");
  toast.id = "undo-toast";
  toast.dataset.todoIds = e.detail.ids;
  toast.dataset.prevStatus = e.detail.prevStatus;
  toast.dataset.label = e.detail.label || "";
  toast.className = "undo-toast";
  toast.style.cssText =
    "background:#fef3c7;color:#78350f;border:1px solid #f59e0b;padding:0.875rem 1.25rem;border-radius:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.2);cursor:pointer;font-weight:600;";
  toast.textContent =
    (e.detail.label || "Item") +
    " " +
    (e.detail.action || "completed") +
    ". (Undo)";

  toast.addEventListener("click", function () {
    htmx.trigger(document.body, "undoRequested");
  });

  document.body.appendChild(toast);
  _undoTimer = setTimeout(function () {
    toast.remove();
  }, 7000);
});

document.body.addEventListener("showUndoConfirm", function (e) {
  var toast = document.getElementById("undo-toast");
  if (!toast) return;
  var label = e.detail.label || "Item";
  toast.textContent = label + " uncompleted. UNDO OK.";
  toast.style.background = "#dcfce7";
  toast.style.color = "#14532d";
  toast.style.borderColor = "#16a34a";
  toast.style.cursor = "default";
  _undoTimer = setTimeout(function () {
    toast.remove();
  }, 2500);
});

document.addEventListener("keydown", function (e) {
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.contentEditable === "true"
  )
    return;

  if (e.key === "Escape") {
    if (document.querySelector(".todo-popover")) {
      e.preventDefault();
      closePopovers();
      return;
    }
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

  // r / [ / ] / u are wired via hyperscript on #done-list and #todo-list.
  // c / p / P / h are wired via hyperscript on the form in _todo_groups.pt.
  // d / f / s / ~ / @ / l field shortcuts are wired via hyperscript in
  // _todo_details_panel.pt.
});


// --- Repetition history panel ---
function openHistoryPanel(itemEl) {
  var url = itemEl.dataset.historyUrl;
  if (!url) return;
  closePopovers();
  closeHistoryPanel();
  fetch(url, { headers: { Accept: "text/html" } })
    .then(function (r) {
      return r.text();
    })
    .then(function (html) {
      var wrap = document.createElement("div");
      wrap.id = "todo-history-wrap";
      wrap.innerHTML = html;
      document.body.appendChild(wrap);
    });
}
function closeHistoryPanel() {
  var w = document.getElementById("todo-history-wrap");
  if (w) w.remove();
}
document.addEventListener("click", function (e) {
  if (e.target.closest(".todo-history-close")) {
    closeHistoryPanel();
    return;
  }
  var rec = e.target.closest(".todo-recurrence");
  if (rec) {
    var item = rec.closest(".todo-item");
    if (item && item.dataset.historyUrl) {
      e.stopPropagation();
      openHistoryPanel(item);
    }
  }
});

// --- Keyboard shortcut help overlay ---
// HTMX swaps body content frequently and removes any element previously
// appended to <body>. We therefore (a) keep `_helpOverlay` as a singleton we
// can re-attach on every load and (b) bind the keydown handler exactly once
// against `document`, which is never replaced.
var _helpOverlay = null;

function _kbdSection(title) {
  return (
    '<p class="text-uppercase fw-semibold text-secondary mb-1 mt-3 small">' +
    title +
    "</p>"
  );
}

function _kbdRow(key, desc) {
  return (
    '<tr class="small">' +
    '<td class="pe-3 text-nowrap align-top pb-1"><kbd>' +
    key +
    "</kbd></td>" +
    '<td class="align-top pb-1 text-body">' +
    desc +
    "</td>" +
    "</tr>"
  );
}

function _kbdCol(sections) {
  return '<div class="col">' + sections.join("") + "</div>";
}

function ensureHelpOverlay() {
  if (_helpOverlay && document.body.contains(_helpOverlay)) return _helpOverlay;
  _helpOverlay = document.createElement("div");
  _helpOverlay.id = "kbd-help-overlay";
  _helpOverlay.className =
    "position-fixed top-0 start-0 w-100 h-100 align-items-center justify-content-center";
  _helpOverlay.style.cssText =
    "display:none;background:rgba(0,0,0,0.45);z-index:9999;";
  var col1 = _kbdCol([
    _kbdSection("Everywhere"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("?", "Show this help"),
    _kbdRow("Esc", "Cancel / close"),
    "</tbody></table>",

    _kbdSection("Todo list"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("click", "Select item \u2014 opens details pane"),
    _kbdRow("c", "Mark selected done"),
    _kbdRow("h", "Put selected on hold"),
    _kbdRow("d", "Set / change due date"),
    _kbdRow("f", "Set / change repetition rule"),
    _kbdRow("s", "Edit tags"),
    _kbdRow("P", "Postpone"),
    _kbdRow("Shift+P", "Postpone selected by 1 day"),
    _kbdRow("[", "Collapse all groups"),
    _kbdRow("]", "Expand all groups"),
    _kbdRow("u", "Undo last action"),
    _kbdRow("click \u21bb", "Show repetition history"),
    "</tbody></table>",

    _kbdSection("Details pane"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("e", "Edit title"),
    _kbdRow("d", "Edit due date"),
    _kbdRow("f", "Edit repetition rule"),
    _kbdRow("s", "Edit tags"),
    _kbdRow("~", "Edit note"),
    _kbdRow("@", "Edit assignees"),
    _kbdRow("l", "Add / edit link"),
    _kbdRow("click field", "Edit that field"),
    _kbdRow("Esc", "Close pane / picker"),
    "</tbody></table>",
  ]);
  var col2 = _kbdCol([
    _kbdSection("Protocol run (in details pane)"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("j / \u2193", "Next item"),
    _kbdRow("k / \u2191", "Previous item"),
    _kbdRow("c", "Mark current done"),
    _kbdRow("t", "Send current to the todo list"),
    _kbdRow("e", "Edit current item before sending"),
    _kbdRow("Esc", "Close details pane"),
    _kbdRow("swipe \u2192", "Same as <kbd>c</kbd>"),
    _kbdRow("swipe \u2190", "Same as <kbd>t</kbd>"),
    "</tbody></table>",

    _kbdSection("Adding a todo"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("#tag", "Attach a tag (single word)"),
    _kbdRow("^", "Open the date picker"),
    _kbdRow("*", "Open the repetition picker"),
    "</tbody></table>",

    _kbdSection("Done list"),
    '<table class="table table-sm table-borderless mb-0"><tbody>',
    _kbdRow("click", "Select / deselect item"),
    _kbdRow("r", "Restore selected items"),
    "</tbody></table>",
  ]);
  _helpOverlay.innerHTML =
    '<div class="card shadow-lg" style="max-width:42rem;width:90%;max-height:90vh;overflow-y:auto;">' +
    '<div class="card-body p-4">' +
    '<h6 class="text-uppercase fw-bold text-secondary small mb-3 mt-0">Keyboard shortcuts</h6>' +
    '<div class="row g-0">' +
    col1 +
    col2 +
    "</div>" +
    "</div></div>";
  document.body.appendChild(_helpOverlay);
  _helpOverlay.addEventListener("click", function (e) {
    if (e.target === _helpOverlay) hideHelp();
  });
  return _helpOverlay;
}

function showHelp() {
  var o = ensureHelpOverlay();
  o.style.display = "flex";
}

function hideHelp() {
  if (_helpOverlay) _helpOverlay.style.display = "none";
}

document.addEventListener("keydown", function (e) {
  if (e.key === "?") {
    var tag = document.activeElement
      ? document.activeElement.tagName.toLowerCase()
      : "";
    if (
      tag === "input" ||
      tag === "textarea" ||
      tag === "select" ||
      (document.activeElement && document.activeElement.isContentEditable)
    )
      return;
    e.preventDefault();
    showHelp();
    return;
  }
  if (
    e.key === "Escape" &&
    _helpOverlay &&
    _helpOverlay.style.display === "flex"
  ) {
    e.preventDefault();
    hideHelp();
  }
});

// --- Details pane -----------------------------------------------------------

var _detailsItemId = null;

function closeDetailsPane() {
  var pane = document.getElementById("details-pane");
  var panel = document.getElementById("details-panel");
  if (pane) pane.classList.add("d-none");
  if (panel) panel.innerHTML = "";
  _detailsItemId = null;
  var bd = document.getElementById("run-panel-backdrop");
  if (bd) bd.parentNode.removeChild(bd);
}

// Keep as alias so templates that still reference closeRunPanel work.
function closeRunPanel() {
  closeDetailsPane();
}

// Details pane close button
document.addEventListener("click", function (e) {
  if (!e.target.closest(".details-close-btn")) return;
  document
    .querySelectorAll("input.todo-checkbox:checked")
    .forEach(function (cb) {
      cb.checked = false;
    });
  closeDetailsPane();
});

// "Start run now" button
document.addEventListener("click", function (e) {
  var btn = e.target.closest(".details-start-run");
  if (!btn) return;
  e.preventDefault();
  var panelUrl = btn.dataset.panelUrl;
  if (!panelUrl) return;
  var runContent = btn.closest(".details-run-content");
  if (runContent)
    runContent.innerHTML = '<div class="p-2 text-muted small">Loading…</div>';
  fetch(panelUrl + "?inline=1")
    .then(function (r) {
      return r.text();
    })
    .then(function (html) {
      if (runContent && runContent.isConnected) {
        runContent.innerHTML = html;
        htmx.process(runContent);
        _runCurrentIdx = 0;
        _runHighlight();
      }
    });
});

// --- Protocol run page interactions ----------------------------------------
//
// Run-item actions (done / send-to-todo / edit) are dispatched via delegation
// on .protocol-run-action buttons inside #protocol-run. Each .protocol-run-item
// carries data-done-url / data-send-url / data-edit-url to keep the JS
// parameter-free.

(function _wireRunActions() {
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".protocol-run-action");
    if (!btn) return;
    var item = btn.closest(".protocol-run-item");
    if (!item) return;
    var action = btn.dataset.action;
    if (action === "edit") return runItemEditInline(item);
    var url = action === "done" ? item.dataset.doneUrl : item.dataset.sendUrl;
    var run = document.getElementById("protocol-run");
    if (!url || !run) return;
    e.preventDefault();
    htmx.ajax("POST", url, { target: run, swap: "innerHTML transition:true" });
  });
})();

function runItemEditInline(itemEl) {
  var textSpan = itemEl.querySelector(".flex-grow-1 > span");
  if (!textSpan) return;
  var existing = textSpan.textContent.trim();
  var input = document.createElement("input");
  input.type = "text";
  input.value = existing;
  input.className = "form-control form-control-sm";
  input.style.maxWidth = "20rem";
  textSpan.replaceWith(input);
  input.focus();
  input.select();
  function commit() {
    var run = document.getElementById("protocol-run");
    var url = itemEl.dataset.editUrl;
    if (!url || !run) return;
    htmx.ajax("POST", url, {
      target: run,
      swap: "innerHTML",
      values: { text: input.value },
    });
  }
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      input.replaceWith(textSpan);
    }
  });
  input.addEventListener("blur", commit);
}

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


// --- Protocol item editor — uses CompositeInput (tags + note only) -----------

function initProtocolItemInputs() {
  document.querySelectorAll(".proto-item-form").forEach(function (form) {
    var container = form.querySelector(".ci-container");
    if (!container) return;
    CompositeInput(container, {
      textOuter: container.querySelector(".ci-text"),
      hiddenInput: form.querySelector(".ci-hidden-input"),
      saveBtn: form.querySelector(".ci-save-btn"),
      form: form,
      tags: true,
      note: true,
      recurrence: false,
      dueDate: false,
      assignees: true,
      principalsUrl: "/todos/principals.json",
    });
  });
}

function initProtocolNewItemInput() {
  var container = document.querySelector(".proto-new-item-ci");
  if (!container) return;
  var form = document.getElementById("proto-new-item-form");
  var protocolId = form ? form.dataset.protocolId : null;
  var sessionKey = protocolId ? "proto-new-item-tags-" + protocolId : null;
  var focusKey = protocolId ? "proto-new-item-focus-" + protocolId : null;

  CompositeInput(container, {
    textOuter: container.querySelector(".ci-text"),
    hiddenInput: form ? form.querySelector(".ci-hidden-input") : null,
    form: form,
    tags: true,
    note: true,
    recurrence: false,
    dueDate: false,
    assignees: true,
    principalsUrl: "/todos/principals.json",
    sessionKey: sessionKey,
    placeholder: "New item…",
  });

  var scrollKey = protocolId ? "proto-scroll-" + protocolId : null;

  if (scrollKey) {
    var savedScroll = sessionStorage.getItem(scrollKey);
    if (savedScroll) {
      sessionStorage.removeItem(scrollKey);
      requestAnimationFrame(function () {
        window.scrollTo({
          top: parseInt(savedScroll, 10),
          behavior: "instant",
        });
      });
    }
  }

  if (focusKey && sessionStorage.getItem(focusKey)) {
    sessionStorage.removeItem(focusKey);
    var seg = container.querySelector(".todo-text-seg");
    if (seg) {
      seg.focus();
    }
  }

  if (form) {
    form.addEventListener("submit", function () {
      if (focusKey) sessionStorage.setItem(focusKey, "1");
      if (scrollKey) sessionStorage.setItem(scrollKey, String(window.scrollY));
    });
  }
}

function deleteProtocolItem(btn) {
  var li = btn.closest("li");
  if (!li) return;
  var url = btn.dataset.deleteUrl;
  var saved = li.outerHTML;
  var placeholder = document.createElement("li");
  placeholder.className = "card mb-1";
  placeholder.innerHTML =
    '<div class="card-body py-1 px-3 d-flex align-items-center gap-2">' +
    '<span class="text-muted small">Item deleted.</span>' +
    '<button type="button" class="btn btn-link btn-sm p-0">Undo</button>' +
    "</div>";
  placeholder._deleteTimer = setTimeout(function () {
    fetch(url, { method: "POST" }).then(function (r) {
      if (!r.ok) {
        placeholder.insertAdjacentHTML("beforebegin", saved);
        placeholder.remove();
      } else {
        placeholder.remove();
      }
    });
  }, 5000);
  placeholder.querySelector("button").addEventListener("click", function () {
    clearTimeout(placeholder._deleteTimer);
    placeholder.insertAdjacentHTML("beforebegin", saved);
    placeholder.remove();
    initProtocolItemInputs();
  });
  li.replaceWith(placeholder);
}

function initProtocolTitleInput() {
  var container = document.getElementById("proto-title-ci");
  if (!container) return;
  var form = document.getElementById("proto-title-form");
  CompositeInput(container, {
    textOuter: container.querySelector(".ci-text"),
    hiddenInput: form ? form.querySelector(".ci-hidden-input") : null,
    quickPickEl: form ? form.querySelector(".ci-quick-pick") : null,
    form: form,
    tags: true,
    note: true,
    recurrence: true,
    dueDate: false,
    assignees: true,
    principalsUrl: "/todos/principals.json",
    placeholder: "Protocol title…",
  });
}

htmx.onLoad(function (content) {
  ensureHelpOverlay();
  initSortables(content);
  initProtocolItemInputs();
  initProtocolTitleInput();
  initProtocolNewItemInput();
  if (document.getElementById("protocol-run")) _runHighlight();
});
ensureHelpOverlay();
initSortables(document);
initProtocolItemInputs();
initProtocolTitleInput();
initProtocolNewItemInput();
if (document.getElementById("protocol-run")) _runHighlight();

function isCaretAtStart(element) {
  // Works only in contentEditable with plaintext-only
  const selection = window.getSelection();
  if (!selection.rangeCount) return false;

  const range = selection.getRangeAt(0);
  return range.collapsed && range.startOffset === 0;
}
