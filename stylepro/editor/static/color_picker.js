/**
 * stylepro/editor/static/color_picker.js
 * ----------------------------------------
 * Standalone color picker widget — vanilla JS, no dependencies.
 * Rendered inside the StylePro editor overlay.
 *
 * Public API (attached to window.StyleProColorPicker):
 *   open(anchorEl, initialColor, onChange, onClose)
 *   close()
 *   getValue() -> string (hex)
 */

(function (global) {
  "use strict";

  // -------------------------------------------------------------------------
  // Utilities
  // -------------------------------------------------------------------------

  function hexToRgb(hex) {
    hex = hex.replace(/^#/, "");
    if (hex.length === 3) hex = hex.split("").map(function(c){ return c+c; }).join("");
    var n = parseInt(hex, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }

  function rgbToHex(r, g, b) {
    return "#" + [r, g, b].map(function(v){
      return Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
    }).join("");
  }

  function hsvToRgb(h, s, v) {
    var i = Math.floor(h / 60) % 6;
    var f = (h / 60) - Math.floor(h / 60);
    var p = v * (1 - s);
    var q = v * (1 - f * s);
    var t = v * (1 - (1 - f) * s);
    var rgb = [[v,t,p],[q,v,p],[p,v,t],[p,q,v],[t,p,v],[v,p,q]][i];
    return { r: Math.round(rgb[0]*255), g: Math.round(rgb[1]*255), b: Math.round(rgb[2]*255) };
  }

  function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b);
    var h, s, v = max;
    var d = max - min;
    s = max === 0 ? 0 : d / max;
    if (max === min) {
      h = 0;
    } else {
      switch (max) {
        case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
        case g: h = ((b - r) / d + 2) / 6; break;
        case b: h = ((r - g) / d + 4) / 6; break;
      }
    }
    return { h: h * 360, s: s, v: v };
  }

  // -------------------------------------------------------------------------
  // ColorPicker class
  // -------------------------------------------------------------------------

  function ColorPicker() {
    this._panel = null;
    this._onChange = null;
    this._onClose = null;
    this._currentHex = "#000000";
    this._hsv = { h: 0, s: 0, v: 0 };
    this._draggingCanvas = false;
    this._draggingHue = false;
    this._boundClose = this._handleOutsideClick.bind(this);
    this._recentColors = this._loadRecent();
  }

  ColorPicker.prototype._loadRecent = function() {
    try {
      return JSON.parse(sessionStorage.getItem("sp_recent_colors") || "[]");
    } catch(e) { return []; }
  };

  ColorPicker.prototype._saveRecent = function(hex) {
    var colors = this._recentColors.filter(function(c){ return c !== hex; });
    colors.unshift(hex);
    this._recentColors = colors.slice(0, 8);
    try {
      sessionStorage.setItem("sp_recent_colors", JSON.stringify(this._recentColors));
    } catch(e) {}
  };

  ColorPicker.prototype.open = function(anchorEl, initialColor, onChange, onClose) {
    if (this._panel) this.close();

    this._onChange = onChange || function(){};
    this._onClose = onClose || function(){};
    this._currentHex = initialColor || "#000000";

    try {
      var rgb = hexToRgb(this._currentHex);
      this._hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
    } catch(e) {
      this._hsv = { h: 0, s: 0, v: 1 };
    }

    this._panel = this._buildPanel();
    document.body.appendChild(this._panel);
    this._positionPanel(anchorEl);
    this._renderCanvas();
    this._updateHueSlider();
    this._updateHexInput();
    this._updatePreview();

    setTimeout(function() {
      document.addEventListener("mousedown", this._boundClose);
    }.bind(this), 0);
  };

  ColorPicker.prototype.close = function() {
    if (this._panel && this._panel.parentNode) {
      this._panel.parentNode.removeChild(this._panel);
    }
    this._panel = null;
    document.removeEventListener("mousedown", this._boundClose);
    if (this._onClose) this._onClose();
  };

  ColorPicker.prototype.getValue = function() {
    return this._currentHex;
  };

  ColorPicker.prototype._handleOutsideClick = function(e) {
    if (this._panel && !this._panel.contains(e.target)) {
      this.close();
    }
  };

  ColorPicker.prototype._positionPanel = function(anchorEl) {
    if (!anchorEl) return;
    var rect = anchorEl.getBoundingClientRect();
    var panel = this._panel;
    var pw = panel.offsetWidth || 220;
    var ph = panel.offsetHeight || 280;
    var left = rect.left + window.scrollX;
    var top  = rect.bottom + window.scrollY + 4;

    if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
    if (top + ph > window.innerHeight + window.scrollY - 8) {
      top = rect.top + window.scrollY - ph - 4;
    }
    panel.style.left = Math.max(4, left) + "px";
    panel.style.top  = Math.max(4, top)  + "px";
  };

  // -------------------------------------------------------------------------
  // Panel DOM
  // -------------------------------------------------------------------------

  ColorPicker.prototype._buildPanel = function() {
    var self = this;
    var panel = document.createElement("div");
    panel.id = "sp-color-picker-panel";
    panel.style.cssText = [
      "position:absolute",
      "z-index:2147483647",
      "background:#1e1e2e",
      "border:1px solid #45475a",
      "border-radius:8px",
      "padding:12px",
      "width:220px",
      "box-shadow:0 8px 24px rgba(0,0,0,0.5)",
      "font-family:system-ui,sans-serif",
      "font-size:12px",
      "color:#cdd6f4",
      "user-select:none",
    ].join(";");

    // Saturation/value canvas
    var canvas = document.createElement("canvas");
    canvas.width = 196; canvas.height = 130;
    canvas.style.cssText = "display:block;border-radius:4px;cursor:crosshair;margin-bottom:8px;";
    canvas.addEventListener("mousedown", function(e) {
      self._draggingCanvas = true;
      self._handleCanvasDrag(e, canvas);
    });
    this._canvas = canvas;

    // Hue slider
    var hueCanvas = document.createElement("canvas");
    hueCanvas.width = 196; hueCanvas.height = 16;
    hueCanvas.style.cssText = "display:block;border-radius:4px;cursor:pointer;margin-bottom:8px;";
    hueCanvas.addEventListener("mousedown", function(e) {
      self._draggingHue = true;
      self._handleHueDrag(e, hueCanvas);
    });
    this._hueCanvas = hueCanvas;

    // Hex input row
    var inputRow = document.createElement("div");
    inputRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px;";

    var preview = document.createElement("div");
    preview.style.cssText = "width:24px;height:24px;border-radius:4px;border:1px solid #45475a;flex-shrink:0;";
    this._preview = preview;

    var hexInput = document.createElement("input");
    hexInput.type = "text";
    hexInput.maxLength = 7;
    hexInput.style.cssText = [
      "flex:1",
      "background:#313244",
      "border:1px solid #45475a",
      "border-radius:4px",
      "color:#cdd6f4",
      "padding:4px 6px",
      "font-size:12px",
      "font-family:monospace",
    ].join(";");
    hexInput.addEventListener("input", function() {
      var val = hexInput.value;
      if (/^#?[0-9a-fA-F]{6}$/.test(val)) {
        var hex = val.startsWith("#") ? val : "#" + val;
        self._setHex(hex);
        self._renderCanvas();
        self._updateHueSlider();
        self._updatePreview();
        self._emitChange();
      }
    });
    this._hexInput = hexInput;

    inputRow.appendChild(preview);
    inputRow.appendChild(hexInput);

    // Recent colors
    var recentRow = document.createElement("div");
    recentRow.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;";
    this._recentRow = recentRow;
    this._renderRecentColors();

    // Done button
    var doneBtn = document.createElement("button");
    doneBtn.textContent = "Apply";
    doneBtn.style.cssText = [
      "margin-top:8px",
      "width:100%",
      "background:#6366f1",
      "color:#fff",
      "border:none",
      "border-radius:4px",
      "padding:6px",
      "cursor:pointer",
      "font-size:12px",
    ].join(";");
    doneBtn.addEventListener("click", function() {
      self._saveRecent(self._currentHex);
      self.close();
    });

    panel.appendChild(canvas);
    panel.appendChild(hueCanvas);
    panel.appendChild(inputRow);
    panel.appendChild(recentRow);
    panel.appendChild(doneBtn);

    // Global mouse move / up for drag
    var mousemove = function(e) {
      if (self._draggingCanvas) self._handleCanvasDrag(e, canvas);
      if (self._draggingHue)    self._handleHueDrag(e, hueCanvas);
    };
    var mouseup = function() {
      self._draggingCanvas = false;
      self._draggingHue = false;
    };
    document.addEventListener("mousemove", mousemove);
    document.addEventListener("mouseup", mouseup);

    // Cleanup on close
    var origClose = this.close.bind(this);
    this.close = function() {
      document.removeEventListener("mousemove", mousemove);
      document.removeEventListener("mouseup", mouseup);
      origClose();
    };

    return panel;
  };

  ColorPicker.prototype._renderRecentColors = function() {
    var self = this;
    var row = this._recentRow;
    if (!row) return;
    row.innerHTML = "";
    this._recentColors.forEach(function(hex) {
      var swatch = document.createElement("div");
      swatch.title = hex;
      swatch.style.cssText = [
        "width:18px","height:18px","border-radius:3px",
        "cursor:pointer","border:1px solid #45475a",
        "background:" + hex,
      ].join(";");
      swatch.addEventListener("click", function() {
        self._setHex(hex);
        self._renderCanvas();
        self._updateHueSlider();
        self._updateHexInput();
        self._updatePreview();
        self._emitChange();
      });
      row.appendChild(swatch);
    });
  };

  // -------------------------------------------------------------------------
  // Canvas rendering
  // -------------------------------------------------------------------------

  ColorPicker.prototype._renderCanvas = function() {
    if (!this._canvas) return;
    var ctx = this._canvas.getContext("2d");
    var w = this._canvas.width, h = this._canvas.height;
    // White to saturated hue gradient (horizontal)
    var hueRgb = hsvToRgb(this._hsv.h, 1, 1);
    var hueColor = "rgb(" + hueRgb.r + "," + hueRgb.g + "," + hueRgb.b + ")";
    var gradH = ctx.createLinearGradient(0, 0, w, 0);
    gradH.addColorStop(0, "#fff");
    gradH.addColorStop(1, hueColor);
    ctx.fillStyle = gradH;
    ctx.fillRect(0, 0, w, h);
    // Transparent to black gradient (vertical)
    var gradV = ctx.createLinearGradient(0, 0, 0, h);
    gradV.addColorStop(0, "rgba(0,0,0,0)");
    gradV.addColorStop(1, "rgba(0,0,0,1)");
    ctx.fillStyle = gradV;
    ctx.fillRect(0, 0, w, h);
    // Draw cursor
    var cx = this._hsv.s * w;
    var cy = (1 - this._hsv.v) * h;
    ctx.beginPath();
    ctx.arc(cx, cy, 6, 0, Math.PI * 2);
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 7, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(0,0,0,0.5)";
    ctx.lineWidth = 1;
    ctx.stroke();
  };

  ColorPicker.prototype._updateHueSlider = function() {
    if (!this._hueCanvas) return;
    var ctx = this._hueCanvas.getContext("2d");
    var w = this._hueCanvas.width, h = this._hueCanvas.height;
    var grad = ctx.createLinearGradient(0, 0, w, 0);
    var stops = [0,60,120,180,240,300,360];
    stops.forEach(function(deg) {
      var rgb = hsvToRgb(deg, 1, 1);
      grad.addColorStop(deg/360, "rgb("+rgb.r+","+rgb.g+","+rgb.b+")");
    });
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
    // Cursor
    var x = (this._hsv.h / 360) * w;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 3, 1, 6, h - 2);
  };

  ColorPicker.prototype._handleCanvasDrag = function(e, canvas) {
    var rect = canvas.getBoundingClientRect();
    var x = Math.max(0, Math.min(canvas.width,  e.clientX - rect.left));
    var y = Math.max(0, Math.min(canvas.height, e.clientY - rect.top));
    this._hsv.s = x / canvas.width;
    this._hsv.v = 1 - y / canvas.height;
    this._syncHexFromHsv();
    this._renderCanvas();
    this._updateHexInput();
    this._updatePreview();
    this._emitChange();
  };

  ColorPicker.prototype._handleHueDrag = function(e, hueCanvas) {
    var rect = hueCanvas.getBoundingClientRect();
    var x = Math.max(0, Math.min(hueCanvas.width, e.clientX - rect.left));
    this._hsv.h = (x / hueCanvas.width) * 360;
    this._syncHexFromHsv();
    this._renderCanvas();
    this._updateHueSlider();
    this._updateHexInput();
    this._updatePreview();
    this._emitChange();
  };

  ColorPicker.prototype._syncHexFromHsv = function() {
    var rgb = hsvToRgb(this._hsv.h, this._hsv.s, this._hsv.v);
    this._currentHex = rgbToHex(rgb.r, rgb.g, rgb.b);
  };

  ColorPicker.prototype._setHex = function(hex) {
    this._currentHex = hex;
    try {
      var rgb = hexToRgb(hex);
      this._hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
    } catch(e) {}
  };

  ColorPicker.prototype._updateHexInput = function() {
    if (this._hexInput) this._hexInput.value = this._currentHex;
  };

  ColorPicker.prototype._updatePreview = function() {
    if (this._preview) this._preview.style.background = this._currentHex;
  };

  ColorPicker.prototype._emitChange = function() {
    if (this._onChange) this._onChange(this._currentHex);
  };

  // -------------------------------------------------------------------------
  // Singleton export
  // -------------------------------------------------------------------------

  var instance = new ColorPicker();

  global.StyleProColorPicker = {
    open: function(anchorEl, initialColor, onChange, onClose) {
      instance.open(anchorEl, initialColor, onChange, onClose);
    },
    close: function() { instance.close(); },
    getValue: function() { return instance.getValue(); },
  };

  if (global.StylePro) global.StylePro.colorPicker = global.StyleProColorPicker;

})(window);
