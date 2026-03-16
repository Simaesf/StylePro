/**
 * stylepro/editor/static/editor.js
 * ----------------------------------
 * StylePro canvas editor -- vanilla JS, no dependencies.
 *
 * Modules:
 *   ConfigReader        -- reads window.STYLEPRO_CONFIG
 *   UndoRedoManager     -- action history stack, Ctrl+Z / Ctrl+Y
 *   CSSVariableManager  -- live CSS variable updates + sessionStorage
 *   ElementIdentifier   -- deterministic data-sp-id on hover
 *   EditOverlay         -- Shadow DOM: resize handles, move handle, color trigger
 *   MenuIntegration     -- toggle UI: hamburger menu (Streamlit) or FAB (Dash/other)
 *   MultiSelect         -- Ctrl+Click group selection + group drag
 *   StyleProEditor      -- activate / deactivate + event coordination
 *   SaveManager         -- POST to API + activate theme for permanent persistence
 *   KeyboardHandler     -- Escape, Ctrl+S, Ctrl+Z, Ctrl+Y, arrow nudge
 *   Toast               -- lightweight notification
 *
 * window.STYLEPRO_CONFIG must be set before this script executes.
 */

(function (global) {
  "use strict";

  // =========================================================================
  // ConfigReader
  // =========================================================================

  var ConfigReader = {
    get: function () { return global.STYLEPRO_CONFIG || {}; },
    role: function () { return (this.get().role || "guest").toLowerCase(); },
    apiUrl: function () { return this.get().api_url || "http://127.0.0.1:5001"; },
    sessionId: function () { return this.get().session_id || ""; },
    themeName: function () { return this.get().theme_name || "default"; },
    varPrefix: function () { return this.get().css_var_prefix || "--sp"; },
    isAdmin: function () { return this.role() === "admin"; },
    canEdit: function () {
      var r = this.role();
      return r === "admin" || r === "user";
    },
    canEditLayout: function () {
      // Only admin/developer can resize and move elements
      return this.isAdmin();
    },
    framework: function () { return (this.get().framework || "unknown").toLowerCase(); },
  };

  // =========================================================================
  // Toast
  // =========================================================================

  var Toast = {
    _el: null,
    _timer: null,
    show: function (msg, type) {
      if (!this._el) {
        this._el = document.createElement("div");
        this._el.style.cssText = [
          "position:fixed", "bottom:24px", "left:50%",
          "transform:translateX(-50%)", "z-index:2147483647",
          "background:#1e1e2e", "color:#cdd6f4", "padding:10px 20px",
          "border-radius:6px", "font-size:13px", "font-family:system-ui,sans-serif",
          "box-shadow:0 4px 12px rgba(0,0,0,0.35)", "transition:opacity 0.2s ease",
          "pointer-events:none",
        ].join(";");
        document.body.appendChild(this._el);
      }
      this._el.textContent = msg;
      this._el.style.background = type === "error" ? "#f38ba8" : "#1e1e2e";
      this._el.style.color = type === "error" ? "#1e1e2e" : "#cdd6f4";
      this._el.style.opacity = "1";
      clearTimeout(this._timer);
      this._timer = setTimeout(function () { Toast._el.style.opacity = "0"; }, 3000);
    },
  };

  // =========================================================================
  // UndoRedoManager
  // =========================================================================

  var UndoRedoManager = {
    _undoStack: [],   // [{varName, oldValue, newValue, selector}]
    _redoStack: [],
    _maxHistory: 200,

    record: function (varName, oldValue, newValue, selector) {
      this._undoStack.push({
        varName: varName,
        oldValue: oldValue,
        newValue: newValue,
        selector: selector || null,
      });
      if (this._undoStack.length > this._maxHistory) {
        this._undoStack.shift();
      }
      // New action clears redo history
      this._redoStack = [];
    },

    undo: function () {
      if (this._undoStack.length === 0) {
        Toast.show("Nothing to undo.");
        return;
      }
      var action = this._undoStack.pop();
      this._redoStack.push(action);

      // Revert: apply oldValue (null means remove)
      if (action.oldValue === null) {
        CSSVariableManager.remove(action.varName, action.selector);
      } else {
        CSSVariableManager.applyNoRecord(action.varName, action.oldValue, action.selector);
      }
      Toast.show("Undo: " + action.varName);
    },

    redo: function () {
      if (this._redoStack.length === 0) {
        Toast.show("Nothing to redo.");
        return;
      }
      var action = this._redoStack.pop();
      this._undoStack.push(action);

      CSSVariableManager.applyNoRecord(action.varName, action.newValue, action.selector);
      Toast.show("Redo: " + action.varName);
    },

    clear: function () {
      this._undoStack = [];
      this._redoStack = [];
    },
  };

  // =========================================================================
  // CSSVariableManager
  // =========================================================================

  var CSSVariableManager = {
    _changes: {},  // key -> { value, selector }
    _sessionKey: function () { return "sp_changes_" + ConfigReader.sessionId(); },

    _changeKey: function (varName, selector) {
      return selector ? varName + "|" + selector : varName;
    },

    apply: function (varName, value, selector) {
      var key = this._changeKey(varName, selector);
      var oldValue = this._changes[key] ? this._changes[key].value : null;
      UndoRedoManager.record(varName, oldValue, value, selector);
      this._changes[key] = { value: value, selector: selector || null, varName: varName };
      this._applyToDom(varName, value, selector);
      this._persist();
    },

    applyNoRecord: function (varName, value, selector) {
      var key = this._changeKey(varName, selector);
      this._changes[key] = { value: value, selector: selector || null, varName: varName };
      this._applyToDom(varName, value, selector);
      this._persist();
    },

    remove: function (varName, selector) {
      var key = this._changeKey(varName, selector);
      delete this._changes[key];
      if (!selector) {
        if (varName.indexOf("--") === 0) {
          document.documentElement.style.removeProperty(varName);
        } else {
          document.documentElement.style[varName] = "";
        }
      } else {
        var styleId = "sp-scoped-" + key.replace(/[^a-zA-Z0-9]/g, "_");
        var el = document.getElementById(styleId);
        if (el) el.parentNode.removeChild(el);
      }
      this._persist();
    },

    _applyToDom: function (varName, value, selector) {
      var isCustomProp = varName.indexOf("--") === 0;
      if (!selector) {
        if (isCustomProp) {
          document.documentElement.style.setProperty(varName, value);
        } else {
          document.documentElement.style[varName] = value;
        }
      } else {
        var key = this._changeKey(varName, selector);
        var styleId = "sp-scoped-" + key.replace(/[^a-zA-Z0-9]/g, "_");
        var el = document.getElementById(styleId);
        if (!el) {
          el = document.createElement("style");
          el.id = styleId;
          document.head.appendChild(el);
        }
        // Regular CSS properties need !important to override framework styles
        // (e.g. Streamlit's button background). CSS custom properties do not.
        var decl = isCustomProp
          ? (varName + ": " + value + ";")
          : (varName + ": " + value + " !important;");
        el.textContent = selector + " { " + decl + " }";
      }
    },

    getAll: function () { return JSON.parse(JSON.stringify(this._changes)); },

    reset: function () {
      this._changes = {};
      UndoRedoManager.clear();
      try { sessionStorage.removeItem(this._sessionKey()); } catch (e) {}
    },

    _persist: function () {
      try {
        sessionStorage.setItem(this._sessionKey(), JSON.stringify(this._changes));
      } catch (e) {}
    },

    restore: function () {
      try {
        var raw = sessionStorage.getItem(this._sessionKey());
        if (!raw) return;
        var saved = JSON.parse(raw);
        var self = this;
        Object.keys(saved).forEach(function (k) {
          self._changes[k] = saved[k];
          self._applyToDom(saved[k].varName || k, saved[k].value, saved[k].selector);
        });
      } catch (e) {}
    },
  };

  // =========================================================================
  // ElementIdentifier
  // =========================================================================

  var ElementIdentifier = {
    _attr: "data-sp-id",

    getId: function (el) { return el.getAttribute(this._attr); },

    ensure: function (el) {
      if (el.getAttribute(this._attr)) return el.getAttribute(this._attr);
      var id = this._computeId(el);
      el.setAttribute(this._attr, id);
      return id;
    },

    _computeId: function (el) {
      // Assign a global document-order index: "button-3" = the 4th <button>
      // in the page (excluding StylePro's own overlay and Streamlit's header).
      // This is simpler and more stable than a DOM-path hash — for the same
      // app code, Streamlit always renders the same components in the same
      // document order, so these IDs are identical on every page load.
      var tag = el.tagName.toLowerCase();
      var host   = document.getElementById("sp-overlay-host");
      var header = document.querySelector('[data-testid="stHeader"]');
      var all = document.body.querySelectorAll(tag);
      var count = 0;
      for (var i = 0; i < all.length; i++) {
        var cand = all[i];
        if (host   && (cand === host   || host.contains(cand)))   continue;
        if (header && (cand === header || header.contains(cand))) continue;
        if (cand === el) return tag + "-" + count;
        count++;
      }
      // Fallback (element not found — should not happen in practice).
      return tag + "-" + count;
    },

    selector: function (id) {
      return "[" + this._attr + "='" + id + "']";
    },
  };

  // =========================================================================
  // LockedElements
  // =========================================================================
  // Per-element lock: locked elements are skipped in canvas edit mode.
  // Lock state is stored in sessionStorage so it survives Streamlit reruns.

  var LockedElements = {
    _sessionKey: "sp_locked_elements",
    _ids: null,

    _load: function () {
      if (this._ids !== null) return;
      try {
        var raw = sessionStorage.getItem(this._sessionKey);
        this._ids = raw ? JSON.parse(raw) : [];
      } catch (e) { this._ids = []; }
    },

    isLocked: function (el) {
      if (!el || el === document.body) return false;
      this._load();
      var id = el.getAttribute("data-sp-id");
      if (id && this._ids.indexOf(id) !== -1) return true;
      // Also treat the element itself as locked if a parent is locked
      var node = el.parentNode;
      while (node && node !== document.body) {
        var pid = node.getAttribute ? node.getAttribute("data-sp-id") : null;
        if (pid && this._ids.indexOf(pid) !== -1) return true;
        node = node.parentNode;
      }
      return false;
    },

    // Returns true if the element is now locked (after toggle).
    toggle: function (el) {
      this._load();
      var id = ElementIdentifier.ensure(el);
      var idx = this._ids.indexOf(id);
      if (idx === -1) {
        this._ids.push(id);
        el.setAttribute("data-sp-locked", "true");
      } else {
        this._ids.splice(idx, 1);
        el.removeAttribute("data-sp-locked");
      }
      this._persist();
      return this._ids.indexOf(id) !== -1;
    },

    // Re-apply the data-sp-locked attribute on page load / rerun.
    restoreVisuals: function () {
      this._load();
      this._ids.forEach(function (id) {
        var el = document.querySelector("[data-sp-id='" + id + "']");
        if (el) el.setAttribute("data-sp-locked", "true");
      });
    },

    _persist: function () {
      try {
        sessionStorage.setItem(this._sessionKey, JSON.stringify(this._ids));
      } catch (e) {}
    },
  };

  // =========================================================================
  // EditOverlay  (Shadow DOM panel)
  // =========================================================================

  var EditOverlay = {
    _host: null,
    _shadow: null,
    _target: null,
    _locked: false,

    init: function () {
      if (this._host) return;
      this._host = document.createElement("div");
      this._host.id = "sp-overlay-host";
      this._host.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:2147483646;";
      document.body.appendChild(this._host);
      this._shadow = this._host.attachShadow({ mode: "open" });
      this._shadow.innerHTML = this._template();
      this._bindHandles();
    },

    _template: function () {
      var canLayout = ConfigReader.canEditLayout();
      var handleDisplay = canLayout ? "block" : "none";
      var moveDisplay = canLayout ? "block" : "none";

      return [
        "<style>",
        "  :host { display:block; position:absolute; top:0; left:0; pointer-events:none; }",
        "  #sp-box { display:none; position:absolute; pointer-events:none; box-sizing:border-box; }",
        "  #sp-box.visible { display:block; }",
        "  .sp-handle {",
        "    position:absolute; width:8px; height:8px;",
        "    background:#6366f1; border:1px solid #fff; border-radius:2px;",
        "    pointer-events:all; box-sizing:border-box; cursor:pointer;",
        "    display:" + handleDisplay + ";",
        "  }",
        "  .sp-handle[data-pos=nw]{top:-4px;left:-4px;cursor:nw-resize;}",
        "  .sp-handle[data-pos=n] {top:-4px;left:calc(50% - 4px);cursor:n-resize;}",
        "  .sp-handle[data-pos=ne]{top:-4px;right:-4px;cursor:ne-resize;}",
        "  .sp-handle[data-pos=e] {top:calc(50% - 4px);right:-4px;cursor:e-resize;}",
        "  .sp-handle[data-pos=se]{bottom:-4px;right:-4px;cursor:se-resize;}",
        "  .sp-handle[data-pos=s] {bottom:-4px;left:calc(50% - 4px);cursor:s-resize;}",
        "  .sp-handle[data-pos=sw]{bottom:-4px;left:-4px;cursor:sw-resize;}",
        "  .sp-handle[data-pos=w] {top:calc(50% - 4px);left:-4px;cursor:w-resize;}",
        "  #sp-move-btn {",
        "    position:absolute; top:-24px; left:50%; transform:translateX(-50%);",
        "    background:#6366f1; color:#fff; border:none; border-radius:4px;",
        "    padding:2px 8px; font-size:11px; font-family:system-ui,sans-serif;",
        "    cursor:move; pointer-events:all; white-space:nowrap;",
        "    display:" + moveDisplay + ";",
        "  }",
        "  #sp-toolbar {",
        "    position:absolute; bottom:-36px; left:0; display:flex; gap:4px;",
        "    pointer-events:all;",
        "  }",
        "  .sp-tb-btn {",
        "    background:#6366f1; color:#fff; border:none; border-radius:4px;",
        "    padding:3px 8px; font-size:11px; font-family:system-ui,sans-serif;",
        "    cursor:pointer; white-space:nowrap;",
        "  }",
        "  .sp-tb-btn:hover { background:#4f46e5; }",
        "  .sp-tb-btn--lock.locked { background:#9ca3af; }",
        "  .sp-tb-btn--lock.locked:hover { background:#6b7280; }",
        "</style>",
        "<div id='sp-box'>",
        "  <div class='sp-handle' data-pos='nw'></div>",
        "  <div class='sp-handle' data-pos='n'></div>",
        "  <div class='sp-handle' data-pos='ne'></div>",
        "  <div class='sp-handle' data-pos='e'></div>",
        "  <div class='sp-handle' data-pos='se'></div>",
        "  <div class='sp-handle' data-pos='s'></div>",
        "  <div class='sp-handle' data-pos='sw'></div>",
        "  <div class='sp-handle' data-pos='w'></div>",
        "  <div id='sp-move-btn'>move</div>",
        "  <div id='sp-toolbar'>",
        "    <button class='sp-tb-btn' data-action='bg'>BG color</button>",
        "    <button class='sp-tb-btn' data-action='text'>Text color</button>",
        "    <button class='sp-tb-btn' data-action='border'>Border color</button>",
        "    <button class='sp-tb-btn sp-tb-btn--lock' id='sp-lock-btn' data-action='lock'>Lock</button>",
        "  </div>",
        "</div>",
      ].join("\n");
    },

    _bindHandles: function () {
      var self = this;

      // Resize handles (admin only — already hidden via CSS for non-admin)
      this._shadow.querySelectorAll(".sp-handle").forEach(function (handle) {
        handle.addEventListener("mousedown", function (e) {
          if (!ConfigReader.canEditLayout()) return;
          e.stopPropagation();
          self._startResize(e, handle.dataset.pos);
        });
      });

      // Move button (admin only)
      var moveBtn = this._shadow.getElementById("sp-move-btn");
      moveBtn.addEventListener("mousedown", function (e) {
        if (!ConfigReader.canEditLayout()) return;
        e.stopPropagation();
        self._startMove(e);
      });

      // Color toolbar buttons
      this._shadow.querySelectorAll(".sp-tb-btn[data-action='bg']," +
          ".sp-tb-btn[data-action='text'],.sp-tb-btn[data-action='border']")
        .forEach(function (btn) {
          btn.addEventListener("click", function (e) {
            e.stopPropagation();
            self._handleColorAction(btn.dataset.action, btn);
          });
        });

      // Lock button — toggle element lock state
      var lockBtn = this._shadow.getElementById("sp-lock-btn");
      lockBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (!self._target) return;
        var nowLocked = LockedElements.toggle(self._target);
        self._updateLockBtn(nowLocked);
        if (nowLocked) {
          // Deselect after locking so user can't accidentally keep editing it
          StyleProEditor.deactivateOverlay();
        }
      });
    },

    _updateLockBtn: function (isLocked) {
      var btn = this._shadow.getElementById("sp-lock-btn");
      if (!btn) return;
      btn.textContent = isLocked ? "Unlock" : "Lock";
      if (isLocked) {
        btn.classList.add("locked");
      } else {
        btn.classList.remove("locked");
      }
    },

    attach: function (target) {
      this._target = target;
      this._updateLockBtn(LockedElements.isLocked(target));
      this._reposition();
    },

    detach: function () {
      var box = this._shadow.getElementById("sp-box");
      if (box) box.classList.remove("visible");
      this._target = null;
      this._locked = false;
    },

    lock: function () { this._locked = true; },
    isLocked: function () { return this._locked; },

    _reposition: function () {
      if (!this._target) return;
      var rect = this._target.getBoundingClientRect();
      var scrollX = window.scrollX || window.pageXOffset;
      var scrollY = window.scrollY || window.pageYOffset;
      var box = this._shadow.getElementById("sp-box");
      box.style.left   = (rect.left + scrollX) + "px";
      box.style.top    = (rect.top  + scrollY) + "px";
      box.style.width  = rect.width  + "px";
      box.style.height = rect.height + "px";
      box.classList.add("visible");
    },

    update: function () {
      if (this._target && this._locked) this._reposition();
    },

    // --- Resize (admin only) ---

    _startResize: function (e, pos) {
      if (!this._target) return;
      var self = this;
      var rect = this._target.getBoundingClientRect();
      var startX = e.clientX, startY = e.clientY;
      var startW = rect.width, startH = rect.height;
      var spId = ElementIdentifier.ensure(this._target);
      var sel  = ElementIdentifier.selector(spId);
      var lastW = startW, lastH = startH;

      function onMove(ev) {
        var dx = ev.clientX - startX, dy = ev.clientY - startY;
        var newW = startW, newH = startH;
        if (pos.includes("e"))  newW = Math.max(20, startW + dx);
        if (pos.includes("s"))  newH = Math.max(20, startH + dy);
        if (pos.includes("w"))  newW = Math.max(20, startW - dx);
        if (pos.includes("n"))  newH = Math.max(20, startH - dy);

        // Live preview: update scoped style tag directly without recording to undo stack.
        if (newW !== lastW) {
          CSSVariableManager._applyToDom("width", Math.round(newW) + "px", sel);
          lastW = newW;
        }
        if (newH !== lastH) {
          CSSVariableManager._applyToDom("height", Math.round(newH) + "px", sel);
          lastH = newH;
        }
        self._reposition();
      }

      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup",  onUp);
        // Commit final size to undo stack once, then clear any inline style.
        if (Math.abs(lastW - startW) > 0.5) {
          CSSVariableManager.apply("width",  Math.round(lastW) + "px", sel);
        }
        if (Math.abs(lastH - startH) > 0.5) {
          CSSVariableManager.apply("height", Math.round(lastH) + "px", sel);
        }
        self._target.style.width  = "";
        self._target.style.height = "";
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup",  onUp);
    },

    // --- Move (admin only) ---

    _startMove: function (e) {
      if (!this._target) return;
      var self = this;
      var startX = e.clientX, startY = e.clientY;

      // Group move: if 2+ elements are selected, move all of them together.
      if (MultiSelect.count() > 1) {
        var group = MultiSelect.startGroupMove(startX, startY);
        function onMoveGroup(ev) { group.onMove(ev); }
        function onUpGroup() {
          document.removeEventListener("mousemove", onMoveGroup);
          document.removeEventListener("mouseup",  onUpGroup);
          group.onUp();
        }
        document.addEventListener("mousemove", onMoveGroup);
        document.addEventListener("mouseup",  onUpGroup);
        return;
      }

      // Single element move.
      var style  = window.getComputedStyle(this._target);
      var startML = parseFloat(style.marginLeft) || 0;
      var startMT = parseFloat(style.marginTop)  || 0;
      var spId = ElementIdentifier.ensure(this._target);
      var sel  = ElementIdentifier.selector(spId);
      var lastML = startML, lastMT = startMT;

      function onMove(ev) {
        var dx = ev.clientX - startX, dy = ev.clientY - startY;
        lastML = startML + dx;
        lastMT = startMT + dy;
        // Live preview: update scoped style tag directly without recording to undo stack.
        CSSVariableManager._applyToDom("margin-left", Math.round(lastML) + "px", sel);
        CSSVariableManager._applyToDom("margin-top",  Math.round(lastMT) + "px", sel);
        self._reposition();
      }

      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup",  onUp);
        // Commit final position to undo stack once, then clear any inline style.
        if (Math.abs(lastML - startML) > 0.5) {
          CSSVariableManager.apply("margin-left", Math.round(lastML) + "px", sel);
        }
        if (Math.abs(lastMT - startMT) > 0.5) {
          CSSVariableManager.apply("margin-top",  Math.round(lastMT) + "px", sel);
        }
        self._target.style.marginLeft = "";
        self._target.style.marginTop  = "";
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup",  onUp);
    },

    // --- Color picker ---

    _handleColorAction: function (action, btn) {
      if (!this._target || !global.StyleProColorPicker) return;
      var self = this;
      var spId = ElementIdentifier.ensure(this._target);
      var computed = window.getComputedStyle(this._target);

      var cssPropMap = { bg: "background-color", text: "color", border: "border-color" };

      var currentColor = computed[cssPropMap[action]] || "#000000";
      currentColor = rgbStringToHex(currentColor) || "#000000";

      global.StyleProColorPicker.open(btn, currentColor, function (hex) {
        // Store as the actual CSS property name (not a CSS variable) so:
        // 1. The scoped style tag uses !important and wins over framework CSS
        // 2. Undo/redo reverts the same property correctly
        // 3. The saved theme generates valid CSS on reload
        // Do NOT set target.style[prop] — the scoped style tag handles it.
        CSSVariableManager.apply(cssPropMap[action], hex, ElementIdentifier.selector(spId));
        self._reposition();
      });
    },
  };

  // =========================================================================
  // MenuIntegration
  // =========================================================================
  // Provides a way to toggle the editor.
  //
  // Streamlit:  injects "StylePro Editor" into the native hamburger menu.
  // Other frameworks (Dash, etc.):  shows a floating action button (FAB).
  //
  // Only shown for admin role (developer option).

  var MenuIntegration = {
    _injected: false,
    _observer: null,
    _fab: null,

    init: function () {
      if (this._injected) return;
      if (!ConfigReader.isAdmin()) return;

      if (ConfigReader.framework() === "streamlit") {
        this._initStreamlitMenu();
      } else {
        this._initFAB();
      }
      this._injected = true;
    },

    // ------------------------------------------------------------------
    // Streamlit: inject item into the hamburger popover menu.
    // ------------------------------------------------------------------
    _initStreamlitMenu: function () {
      var self = this;
      // Streamlit renders the menu lazily (on click). Use MutationObserver.
      this._observer = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
          var added = mutations[i].addedNodes;
          for (var j = 0; j < added.length; j++) {
            if (added[j].nodeType !== 1) continue;
            self._tryInject(added[j]);
          }
        }
      });
      this._observer.observe(document.body, { childList: true, subtree: true });
      this._tryInject(document.body);
    },

    // ------------------------------------------------------------------
    // Non-Streamlit: floating action button in the bottom-right corner.
    // ------------------------------------------------------------------
    _initFAB: function () {
      if (document.getElementById("sp-fab")) return;
      var btn = document.createElement("button");
      btn.id = "sp-fab";
      btn.title = "StylePro Editor";
      btn.innerHTML = _pencilSvg("#ffffff", 18);
      btn.style.cssText = [
        "position:fixed", "bottom:24px", "right:24px", "z-index:2147483646",
        "width:44px", "height:44px", "border-radius:50%",
        "background:#6366f1", "border:none", "cursor:pointer",
        "display:flex", "align-items:center", "justify-content:center",
        "box-shadow:0 4px 12px rgba(99,102,241,0.4)",
        "transition:background 0.2s, box-shadow 0.2s",
      ].join(";");
      btn.addEventListener("mouseenter", function () {
        btn.style.background = "#4f46e5";
        btn.style.boxShadow = "0 6px 16px rgba(99,102,241,0.5)";
      });
      btn.addEventListener("mouseleave", function () {
        btn.style.background = btn.getAttribute("data-active") ? "#4f46e5" : "#6366f1";
        btn.style.boxShadow = "0 4px 12px rgba(99,102,241,0.4)";
      });
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        StyleProEditor.toggle();
      });
      document.body.appendChild(btn);
      this._fab = btn;
    },

    _tryInject: function (root) {
      // Streamlit renders the hamburger menu into a portal element.
      // The selector varies across Streamlit versions; we try several.
      if (!root.querySelectorAll) return;

      var menuContainers = [];
      var selectors = [
        '[data-testid="stMainMenuList"]',          // Streamlit ~1.30
        '[data-testid="stMainMenuPopover"] ul',    // Streamlit ~1.35+
        '[data-baseweb="menu"] ul',                // BaseUI menu component
        '[role="menu"]',                           // ARIA fallback
      ];
      var seen = [];
      selectors.forEach(function (sel) {
        try {
          root.querySelectorAll(sel).forEach(function (el) {
            if (seen.indexOf(el) === -1) {
              seen.push(el);
              menuContainers.push(el);
            }
          });
        } catch (e) {}
      });

      for (var i = 0; i < menuContainers.length; i++) {
        var menu = menuContainers[i];
        if (menu.querySelector("#sp-menu-toggle")) continue;

        // Create separator
        var sep = document.createElement("hr");
        sep.style.cssText = "border:none;border-top:1px solid rgba(128,128,128,0.2);margin:4px 0;";
        menu.appendChild(sep);

        // Create our menu item
        var item = document.createElement("div");
        item.id = "sp-menu-toggle";
        item.setAttribute("role", "menuitem");
        item.tabIndex = 0;
        item.style.cssText = [
          "padding:8px 16px", "cursor:pointer", "font-size:14px",
          "font-family:system-ui,sans-serif", "white-space:nowrap",
          "display:flex", "align-items:center", "gap:8px",
        ].join(";");
        item.innerHTML = _pencilSvg("#6366f1", 14) + " <span>StylePro Editor</span>";

        item.addEventListener("mouseenter", function () {
          item.style.background = "rgba(99,102,241,0.1)";
        });
        item.addEventListener("mouseleave", function () {
          item.style.background = "transparent";
        });
        item.addEventListener("click", function (e) {
          e.stopPropagation();
          // Dispatch Escape BEFORE toggle() so KeyboardHandler is not yet
          // attached when the event fires — otherwise Escape immediately
          // deactivates the editor we're about to activate.
          document.dispatchEvent(new KeyboardEvent("keydown", {
            key: "Escape", keyCode: 27, bubbles: true,
          }));
          StyleProEditor.toggle();
        });

        menu.appendChild(item);
      }
    },

    updateLabel: function (active) {
      // FAB: change colour and tooltip to reflect active state.
      if (this._fab) {
        this._fab.setAttribute("data-active", active ? "1" : "");
        this._fab.style.background = active ? "#4f46e5" : "#6366f1";
        this._fab.title = active ? "Exit StylePro Editor" : "StylePro Editor";
        return;
      }
      // Streamlit hamburger: update injected menu item text.
      var items = document.querySelectorAll("#sp-menu-toggle span");
      for (var i = 0; i < items.length; i++) {
        items[i].textContent = active ? "Exit StylePro Editor" : "StylePro Editor";
      }
    },
  };

  // =========================================================================
  // StyleProEditor
  // =========================================================================

  // =========================================================================
  // MultiSelect
  // =========================================================================
  // Ctrl+Click adds elements to a group. Dragging any member moves the whole
  // group together. Color changes from the toolbar apply to every member.

  var MultiSelect = {
    _items: [],
    CSS_CLASS: "sp-multi-selected",

    add: function (el) {
      if (this._items.indexOf(el) !== -1) return;
      this._items.push(el);
      el.classList.add(this.CSS_CLASS);
    },

    remove: function (el) {
      this._items = this._items.filter(function (e) { return e !== el; });
      el.classList.remove(MultiSelect.CSS_CLASS);
    },

    toggle: function (el) {
      if (this._items.indexOf(el) !== -1) { this.remove(el); return false; }
      this.add(el); return true;
    },

    has: function (el) { return this._items.indexOf(el) !== -1; },

    count: function () { return this._items.length; },

    getAll: function () { return this._items.slice(); },

    clear: function () {
      this._items.forEach(function (el) { el.classList.remove(MultiSelect.CSS_CLASS); });
      this._items = [];
    },

    // Kick off a group move: snapshot every member's current margins, then
    // return an onMove handler that the caller wires up to mousemove.
    startGroupMove: function (startX, startY) {
      var snapshots = this._items.map(function (el) {
        var cs = window.getComputedStyle(el);
        return {
          el: el,
          ml: parseFloat(cs.marginLeft) || 0,
          mt: parseFloat(cs.marginTop)  || 0,
        };
      });

      return {
        onMove: function (ev) {
          var dx = ev.clientX - startX, dy = ev.clientY - startY;
          snapshots.forEach(function (snap) {
            snap.el.style.marginLeft = (snap.ml + dx) + "px";
            snap.el.style.marginTop  = (snap.mt + dy) + "px";
          });
          EditOverlay.update();
        },
        onUp: function () {
          // Persist each member's new position into the CSS change store, then
          // clear inline styles so only the scoped !important rule controls position.
          snapshots.forEach(function (snap) {
            var spId = ElementIdentifier.ensure(snap.el);
            var sel  = ElementIdentifier.selector(spId);
            var cs   = window.getComputedStyle(snap.el);
            var ml = parseFloat(cs.marginLeft) || 0;
            var mt = parseFloat(cs.marginTop)  || 0;
            if (Math.abs(ml - snap.ml) > 0.5) {
              CSSVariableManager.apply("margin-left",  Math.round(ml) + "px", sel);
            }
            if (Math.abs(mt - snap.mt) > 0.5) {
              CSSVariableManager.apply("margin-top", Math.round(mt) + "px", sel);
            }
            snap.el.style.marginLeft = "";
            snap.el.style.marginTop  = "";
          });
        },
      };
    },
  };

  var StyleProEditor = {
    _active: false,
    _hoveredEl: null,
    _sessionKey: function () { return "sp_edit_mode_" + ConfigReader.sessionId(); },

    toggle: function () {
      this._active ? this.deactivate() : this.activate();
    },

    activate: function () {
      if (this._active) return;
      this._active = true;
      document.body.classList.add("sp-canvas-active");
      EditOverlay.init();
      this._attachListeners();
      MenuIntegration.updateLabel(true);
      KeyboardHandler.attach();
      CSSVariableManager.restore();
      Toast.show("StylePro editor active -- hover to select, Ctrl+Z to undo");
      try { sessionStorage.setItem(this._sessionKey(), "1"); } catch(e) {}
    },

    deactivate: function () {
      if (!this._active) return;
      this._active = false;
      document.body.classList.remove("sp-canvas-active");
      EditOverlay.detach();
      MultiSelect.clear();
      this._detachListeners();
      MenuIntegration.updateLabel(false);
      KeyboardHandler.detach();
      if (this._hoveredEl) {
        this._hoveredEl.classList.remove("sp-hovered");
        this._hoveredEl = null;
      }
      try { sessionStorage.removeItem(this._sessionKey()); } catch(e) {}
    },

    restoreFromSession: function () {
      try {
        if (sessionStorage.getItem(this._sessionKey()) === "1") {
          this.activate();
        }
      } catch(e) {}
    },

    _attachListeners: function () {
      document.addEventListener("mouseover",  this._onMouseOver  = this._handleMouseOver.bind(this));
      document.addEventListener("mouseout",   this._onMouseOut   = this._handleMouseOut.bind(this));
      document.addEventListener("click",      this._onClick      = this._handleClick.bind(this), true);
      window.addEventListener("scroll", this._onScroll = function() { EditOverlay.update(); });
    },

    _detachListeners: function () {
      document.removeEventListener("mouseover", this._onMouseOver);
      document.removeEventListener("mouseout",  this._onMouseOut);
      document.removeEventListener("click",     this._onClick, true);
      window.removeEventListener("scroll", this._onScroll);
    },

    _handleMouseOver: function (e) {
      if (EditOverlay.isLocked()) return;
      var target = e.target;
      if (target.closest && (
        target.closest("#sp-save-dialog") ||
        target.closest('[data-testid="stToolbarActions"]') ||
        target.closest('[data-testid="stHeader"]')
      )) return;
      if (!this._isEditable(target)) return;
      if (this._hoveredEl && this._hoveredEl !== target) {
        this._hoveredEl.classList.remove("sp-hovered");
      }
      target.classList.add("sp-hovered");
      this._hoveredEl = target;
      ElementIdentifier.ensure(target);
      EditOverlay.init();
      EditOverlay.attach(target);
    },

    _handleMouseOut: function (e) {
      if (EditOverlay.isLocked()) return;
      var target = e.target;
      if (target === this._hoveredEl) {
        target.classList.remove("sp-hovered");
        this._hoveredEl = null;
        EditOverlay.detach();
      }
    },

    // Collapse the overlay without fully deactivating edit mode.
    deactivateOverlay: function () {
      EditOverlay.detach();
      if (this._hoveredEl) {
        this._hoveredEl.classList.remove("sp-hovered");
        this._hoveredEl = null;
      }
    },

    _handleClick: function (e) {
      if (!this._active) return;
      var target = e.target;
      // Always let save dialog and overlay host handle their own clicks.
      if (target.closest && (
        target.closest("#sp-overlay-host") ||
        target.closest("#sp-menu-toggle") ||
        target.closest("#sp-save-dialog")
      )) return;
      if (!this._isEditable(target)) return;

      e.preventDefault();
      e.stopPropagation();

      // Ctrl/Cmd+Click: toggle element in multi-selection group.
      if (e.ctrlKey || e.metaKey) {
        var added = MultiSelect.toggle(target);
        ElementIdentifier.ensure(target);
        if (added) {
          // Show overlay on the most recently added element for color access.
          EditOverlay.init();
          EditOverlay.attach(target);
          EditOverlay.lock();
        } else if (MultiSelect.count() === 0) {
          EditOverlay.detach();
        }
        Toast.show(
          MultiSelect.count() === 0
            ? "Selection cleared."
            : MultiSelect.count() + " element(s) selected — drag the move handle to move them together."
        );
        return;
      }

      // Normal click: clear any group selection, single-select this element.
      MultiSelect.clear();

      if (EditOverlay.isLocked() && EditOverlay._target === target) {
        EditOverlay._locked = false;
        return;
      }

      EditOverlay.init();
      EditOverlay.attach(target);
      EditOverlay.lock();

      if (this._hoveredEl && this._hoveredEl !== target) {
        this._hoveredEl.classList.remove("sp-hovered");
      }
      target.classList.add("sp-hovered");
      this._hoveredEl = target;
    },

    _isEditable: function (el) {
      if (!el || el === document.body || el === document.documentElement) return false;
      if (el.id === "sp-overlay-host" || el.id === "sp-menu-toggle") return false;
      if (el.closest && el.closest("#sp-overlay-host")) return false;
      if (el.closest && el.closest("#sp-color-picker-panel")) return false;
      if (el.closest && el.closest("#sp-menu-toggle")) return false;
      if (el.closest && el.closest("#sp-save-dialog")) return false;
      // Exclude Streamlit's top toolbar — hamburger, deploy button, etc.
      // Must remain clickable so the user can open the StylePro menu item.
      if (el.closest && el.closest('[data-testid="stToolbarActions"]')) return false;
      if (el.closest && el.closest('[data-testid="stHeader"]')) return false;
      if (LockedElements.isLocked(el)) return false;
      return true;
    },

    nudge: function (axis, px) {
      if (!ConfigReader.canEditLayout()) {
        Toast.show("Layout editing requires admin role.");
        return;
      }
      var target = EditOverlay._target;
      if (!target) return;
      var spId = ElementIdentifier.ensure(target);
      var sel  = ElementIdentifier.selector(spId);
      var style = window.getComputedStyle(target);
      var prop    = axis === "x" ? "marginLeft"   : "marginTop";
      var cssProp = axis === "x" ? "margin-left"  : "margin-top";
      var current = parseFloat(style[prop]) || 0;
      var next = current + px;
      CSSVariableManager.apply(cssProp, Math.round(next) + "px", sel);
      // Clear any inline style so the scoped !important rule controls position.
      target.style[prop] = "";
      EditOverlay._reposition();
    },
  };

  // =========================================================================
  // LocalThemeStore
  // =========================================================================
  // For non-admin (user role): changes persist in localStorage so they
  // survive browser reloads without ever touching the server-side store.

  var LocalThemeStore = {
    _key: function () { return "sp_user_theme_" + ConfigReader.themeName(); },

    save: function (changes) {
      try {
        localStorage.setItem(this._key(), JSON.stringify(changes));
      } catch (e) {
        console.warn("[StylePro] localStorage write failed:", e);
      }
    },

    load: function () {
      try {
        var raw = localStorage.getItem(this._key());
        return raw ? JSON.parse(raw) : null;
      } catch (e) { return null; }
    },

    clear: function () {
      try { localStorage.removeItem(this._key()); } catch (e) {}
    },

    applyIfPresent: function () {
      var saved = this.load();
      if (!saved) return;
      Object.keys(saved).forEach(function (key) {
        var entry = saved[key];
        CSSVariableManager.applyNoRecord(
          entry.varName || key, entry.value, entry.selector
        );
      });
    },
  };

  // =========================================================================
  // SaveDialog
  // =========================================================================
  // Shown when an admin saves: choose override current theme or new theme.

  var SaveDialog = {
    _el: null,

    show: function (onSave) {
      if (this._el) return;
      var self = this;
      var currentName = ConfigReader.get().theme_name || "default";

      var overlay = document.createElement("div");
      overlay.id = "sp-save-dialog";
      overlay.style.cssText = [
        "position:fixed", "top:0", "left:0", "right:0", "bottom:0",
        "background:rgba(0,0,0,0.6)", "z-index:2147483647",
        "display:flex", "align-items:center", "justify-content:center",
      ].join(";");

      var box = document.createElement("div");
      box.style.cssText = [
        "background:#1e1e2e", "color:#cdd6f4", "padding:24px",
        "border-radius:8px", "font-family:system-ui,sans-serif",
        "min-width:300px", "max-width:420px",
        "box-shadow:0 8px 32px rgba(0,0,0,0.5)",
      ].join(";");

      var title = document.createElement("div");
      title.style.cssText = "font-size:15px;font-weight:600;margin-bottom:16px;";
      title.textContent = "Save Theme";
      box.appendChild(title);

      // Radio: override
      box.appendChild(self._radioLabel("sp-save-mode", "override", true,
        "Override \"" + currentName + "\""));

      // Radio: new theme
      box.appendChild(self._radioLabel("sp-save-mode", "new", false,
        "Save as new theme"));

      // Name input (shown when "new" is selected)
      var nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.placeholder = "new_theme_name";
      nameInput.style.cssText = [
        "display:none", "width:100%", "box-sizing:border-box",
        "padding:6px 10px", "margin:8px 0 4px",
        "background:#313244", "border:1px solid #45475a",
        "border-radius:4px", "color:#cdd6f4", "font-size:13px",
      ].join(";");
      box.appendChild(nameInput);

      box.querySelectorAll("input[type=radio]").forEach(function (r) {
        r.addEventListener("change", function () {
          nameInput.style.display = (r.value === "new" && r.checked) ? "block" : "none";
          if (r.value === "new" && r.checked) nameInput.focus();
        });
      });

      // Buttons
      var btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:20px;";

      var cancelBtn = self._btn("Cancel", "#313244");
      cancelBtn.addEventListener("click", function () { self.close(); });

      var saveBtn = self._btn("Save", "#6366f1");
      saveBtn.addEventListener("click", function () {
        var mode = box.querySelector("input[name=sp-save-mode]:checked").value;
        var newName = nameInput.value.trim();
        if (mode === "new" && !newName) {
          nameInput.style.borderColor = "#f38ba8";
          nameInput.focus();
          return;
        }
        self.close();
        onSave(mode === "override" ? currentName : newName);
      });

      // Export CSS link — downloads the current active theme as a standalone
      // CSS file that can be included in the app without StylePro running.
      var exportRow = document.createElement("div");
      exportRow.style.cssText = "margin-top:14px;padding-top:12px;border-top:1px solid #313244;font-size:12px;color:#6c7086;";
      var exportLink = document.createElement("a");
      exportLink.textContent = "Export current theme as CSS (for use without StylePro)";
      exportLink.style.cssText = "color:#6366f1;cursor:pointer;text-decoration:underline;";
      exportLink.addEventListener("click", function (e) {
        e.preventDefault();
        var cfg = ConfigReader.get();
        var name = cfg.theme_name || "default";
        var url = (cfg.api_url || "http://127.0.0.1:5001") + "/themes/" + encodeURIComponent(name) + "/export.css";
        var a = document.createElement("a");
        a.href = url;
        a.download = name + ".css";
        a.click();
      });
      exportRow.appendChild(exportLink);
      box.appendChild(exportRow);

      btnRow.appendChild(cancelBtn);
      btnRow.appendChild(saveBtn);
      box.appendChild(btnRow);
      overlay.appendChild(box);
      document.body.appendChild(overlay);
      this._el = overlay;

      // Close on backdrop click
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) self.close();
      });
      // Escape closes dialog without deactivating editor
      overlay.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { e.stopPropagation(); self.close(); }
      });
    },

    close: function () {
      if (this._el && this._el.parentNode) {
        this._el.parentNode.removeChild(this._el);
      }
      this._el = null;
    },

    _radioLabel: function (name, value, checked, text) {
      var label = document.createElement("label");
      label.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:10px;cursor:pointer;font-size:14px;";
      var radio = document.createElement("input");
      radio.type = "radio"; radio.name = name; radio.value = value;
      radio.checked = checked; radio.style.cursor = "pointer";
      var span = document.createElement("span");
      span.textContent = text;
      label.appendChild(radio);
      label.appendChild(span);
      return label;
    },

    _btn: function (text, bg) {
      var btn = document.createElement("button");
      btn.textContent = text;
      btn.style.cssText = [
        "padding:8px 16px", "background:" + bg, "color:#cdd6f4",
        "border:none", "border-radius:4px", "cursor:pointer",
        "font-size:13px", "font-family:system-ui,sans-serif",
      ].join(";");
      return btn;
    },
  };

  // =========================================================================
  // SaveManager
  // =========================================================================
  // Admin:  shows SaveDialog then saves globally to ThemeStore + activates.
  // User:   saves locally to localStorage (browser-only, personal).
  // Guest:  cannot save.

  var SaveManager = {
    save: function () {
      var changes = CSSVariableManager.getAll();
      if (Object.keys(changes).length === 0) {
        Toast.show("No changes to save.");
        return;
      }

      var role = ConfigReader.role();

      if (role === "admin") {
        SaveDialog.show(function (themeName) {
          SaveManager._saveGlobal(changes, themeName);
        });
      } else if (role === "user") {
        this._saveLocal(changes);
      } else {
        Toast.show("Saving requires at least user role.", "error");
      }
    },

    _saveLocal: function (changes) {
      LocalThemeStore.save(changes);
      Toast.show("Changes saved to your browser (personal theme).");
    },

    _saveGlobal: function (changes, themeName) {
      var cfg = ConfigReader.get();
      var apiUrl = cfg.api_url || "http://127.0.0.1:5001";

      // Use the full change key (property|selector) to avoid collisions when
      // the same CSS property is changed on multiple elements.
      var variables = {};
      Object.keys(changes).forEach(function (key) {
        var entry = changes[key];
        variables[key] = {
          name: entry.varName || key,
          value: entry.value,
          label: entry.varName || key,
          category: "color",
          element_selector: entry.selector || null,
        };
      });

      var payload = JSON.stringify({
        name: themeName,
        variables: variables,
        metadata: { saved_by: cfg.user_id || "editor" },
        role: cfg.role || "admin",
      });

      var xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl + "/themes", true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.onload = function () {
        if (xhr.status === 200) {
          SaveManager._activateTheme(themeName, cfg.role, apiUrl);
        } else {
          var msg = "Save failed (" + xhr.status + ")";
          try { msg = JSON.parse(xhr.responseText).error || msg; } catch(e) {}
          Toast.show(msg, "error");
        }
      };
      xhr.onerror = function () {
        Toast.show("Could not reach StylePro API server.", "error");
      };
      xhr.send(payload);
    },

    _activateTheme: function (name, role, apiUrl) {
      var xhr = new XMLHttpRequest();
      xhr.open("PUT", apiUrl + "/themes/" + encodeURIComponent(name) + "/activate", true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.onload = function () {
        if (xhr.status === 200) {
          Toast.show("Theme saved and applied globally.");
        } else {
          Toast.show("Theme saved (activate requires admin).");
        }
      };
      xhr.onerror = function () {
        Toast.show("Theme saved, but could not activate.", "error");
      };
      xhr.send(JSON.stringify({ role: role }));
    },
  };

  // =========================================================================
  // KeyboardHandler
  // =========================================================================

  var KeyboardHandler = {
    _handler: null,

    attach: function () {
      if (this._handler) return;
      this._handler = function (e) {
        // Escape -- deactivate
        if (e.key === "Escape") {
          StyleProEditor.deactivate();
          return;
        }

        // Ctrl+Z / Cmd+Z -- undo
        if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
          e.preventDefault();
          UndoRedoManager.undo();
          return;
        }

        // Ctrl+Y / Cmd+Y -- redo
        if ((e.ctrlKey || e.metaKey) && e.key === "y") {
          e.preventDefault();
          UndoRedoManager.redo();
          return;
        }

        // Ctrl+S / Cmd+S -- save
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
          e.preventDefault();
          SaveManager.save();
          return;
        }

        // Arrow keys -- nudge (admin only)
        if (e.key === "ArrowLeft")  { e.preventDefault(); StyleProEditor.nudge("x", e.shiftKey ? -10 : -1); }
        if (e.key === "ArrowRight") { e.preventDefault(); StyleProEditor.nudge("x", e.shiftKey ?  10 :  1); }
        if (e.key === "ArrowUp")    { e.preventDefault(); StyleProEditor.nudge("y", e.shiftKey ? -10 : -1); }
        if (e.key === "ArrowDown")  { e.preventDefault(); StyleProEditor.nudge("y", e.shiftKey ?  10 :  1); }
      };
      document.addEventListener("keydown", this._handler);
    },

    detach: function () {
      if (this._handler) {
        document.removeEventListener("keydown", this._handler);
        this._handler = null;
      }
    },
  };

  // =========================================================================
  // Helpers
  // =========================================================================

  function _pencilSvg(color, size) {
    color = color || "#ffffff";
    size = size || 18;
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>';
  }

  function rgbStringToHex(rgb) {
    if (!rgb || rgb === "transparent" || rgb === "rgba(0, 0, 0, 0)") return null;
    if (rgb.startsWith("#")) return rgb;
    var m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!m) return null;
    return "#" + [m[1], m[2], m[3]].map(function(v) {
      return parseInt(v).toString(16).padStart(2, "0");
    }).join("");
  }

  // Assign data-sp-id to every element in the app body (skipping StylePro's
  // own overlay).  This makes saved theme CSS selectors match immediately on
  // page load, so theme changes are visible in the normal app view — not only
  // while hovering in edit mode.
  function _seedAllIds() {
    // Walk every element in document order and assign "tag-N" IDs in a single
    // pass.  This is O(n) and consistent with _computeId's counting logic —
    // both exclude the StylePro overlay host and Streamlit's header toolbar.
    var host   = document.getElementById("sp-overlay-host");
    var header = document.querySelector('[data-testid="stHeader"]');
    var tagCounts = {};
    var all = document.body.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (host   && (el === host   || host.contains(el)))   continue;
      if (header && (el === header || header.contains(el))) continue;
      if (el.getAttribute("data-sp-id")) continue; // already seeded
      var tag = el.tagName.toLowerCase();
      var idx = tagCounts[tag] || 0;
      tagCounts[tag] = idx + 1;
      el.setAttribute("data-sp-id", tag + "-" + idx);
    }
  }

  // Wait for Streamlit to finish its initial render before seeding IDs.
  // Streamlit renders into [data-testid="stAppViewContainer"] after React mounts.
  var _seedObserver = null;
  var _seedDebounce = null;

  function _scheduleSeed() {
    clearTimeout(_seedDebounce);
    _seedDebounce = setTimeout(function () {
      _seedAllIds();
      LockedElements.restoreVisuals();
    }, 150);
  }

  function _seedIdsWhenReady() {
    // Initial seed: poll until Streamlit's container appears (up to 3s).
    var attempts = 0;
    function tryNow() {
      var container = document.querySelector('[data-testid="stAppViewContainer"]');
      if (container && container.querySelectorAll("*").length > 10) {
        _seedAllIds();
        LockedElements.restoreVisuals();
      } else if (attempts < 15) {
        attempts++;
        setTimeout(tryNow, 200);
      }
    }
    tryNow();

    // After initial seed, watch for Streamlit reruns (which wipe and re-render
    // the DOM).  Re-seed after each burst of mutations settles.
    if (!_seedObserver) {
      _seedObserver = new MutationObserver(function (mutations) {
        var significant = false;
        for (var i = 0; i < mutations.length; i++) {
          if (mutations[i].addedNodes.length > 0) { significant = true; break; }
        }
        if (significant) _scheduleSeed();
      });
      var root = document.querySelector('[data-testid="stAppViewContainer"]') || document.body;
      _seedObserver.observe(root, { childList: true, subtree: true });
    }
  }

  function _injectHoverStyle() {
    if (document.getElementById("sp-hover-style")) return;
    var s = document.createElement("style");
    s.id = "sp-hover-style";
    s.textContent = [
      ".sp-hovered{outline:2px solid #6366f1!important;outline-offset:2px!important;cursor:crosshair!important;}",
      // Multi-selected: teal ring so it's visually distinct from the single-select purple.
      ".sp-multi-selected{outline:2px solid #2dd4bf!important;outline-offset:2px!important;}",
      // Locked elements show a muted dashed outline in canvas mode so devs can see them.
      "body.sp-canvas-active [data-sp-locked]{outline:2px dashed #9ca3af!important;outline-offset:2px!important;cursor:not-allowed!important;}",
    ].join("\n");
    document.head.appendChild(s);
  }

  // =========================================================================
  // Boot
  // =========================================================================

  function boot() {
    var cfg = ConfigReader.get();
    if (!cfg.role) {
      console.warn("[StylePro] window.STYLEPRO_CONFIG not set; editor disabled.");
      return;
    }

    _injectHoverStyle();
    _seedIdsWhenReady();
    MenuIntegration.init();

    // For user role: apply personal theme from localStorage on every load
    if (cfg.role === "user") {
      LocalThemeStore.applyIfPresent();
    }

    // Restore session state across Streamlit reruns
    StyleProEditor.restoreFromSession();

    console.log(
      "[StylePro] editor loaded  role=" + cfg.role +
      "  theme=" + cfg.theme_name +
      "  api=" + cfg.api_url
    );
  }

  // =========================================================================
  // Public API
  // =========================================================================

  global.StylePro = {
    activate:      function () { StyleProEditor.activate(); },
    deactivate:    function () { StyleProEditor.deactivate(); },
    save:          function () { SaveManager.save(); },
    undo:          function () { UndoRedoManager.undo(); },
    redo:          function () { UndoRedoManager.redo(); },
    resetChanges:  function () { CSSVariableManager.reset(); },
    refreshConfig: function (cfg) {
      global.STYLEPRO_CONFIG = cfg;
      MenuIntegration.init();
    },
    _editor: StyleProEditor,
    _cssVars: CSSVariableManager,
    _undoRedo: UndoRedoManager,
    _localStore: LocalThemeStore,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

})(window);
