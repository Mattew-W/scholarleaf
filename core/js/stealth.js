/**
 * stealth.js - 反检测注入脚本
 * ============================================================
 * 通过 page.evaluate() 注入到顶层页面，包含：
 *   Part A: 指纹伪装（A1-A12）
 *   Part B: 页面离开保护（B1-B4）
 */
(function() {
    'use strict';

    // ═══════════════════════════════════════════════════════════════════════
    //  Part A: 基本反检测（指纹伪装）
    // ═══════════════════════════════════════════════════════════════════════

    // ── A1. 隐藏 navigator.webdriver ─────────────────────────────────────
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true,
        });
    } catch(e) { /* webdriver 不可配置，保留原值 */ }

    // ── A2. 注入 window.chrome 对象 ─────────────────────────────────────
    if (!window.chrome) {
        window.chrome = {
            app: {
                isInstalled: false,
                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
            },
            runtime: {
                OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                OnRestartRequiredReason: { APP_UPDATE: 'app_update', GC: 'gc', OS_UPDATE: 'os_update' },
                PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
            },
        };
    }

    // ── A3. 模拟插件列表 ────────────────────────────────────────────────
    const _plugins = [
        { name: 'Chrome PDF Plugin',  filename: 'internal-pdf-viewer',       description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer',  filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client',      filename: 'internal-nacl-plugin',       description: '' },
    ];
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const arr = _plugins.map(p => {
                    const plugin = Object.create(Plugin.prototype);
                    Object.defineProperties(plugin, {
                        name:        { value: p.name,        enumerable: true },
                        filename:    { value: p.filename,    enumerable: true },
                        description: { value: p.description, enumerable: true },
                        length:      { value: 0,             enumerable: true },
                    });
                    return plugin;
                });
                arr.item   = (i) => arr[i];
                arr.namedItem = (n) => arr.find(p => p.name === n) || null;
                arr.refresh   = () => {};
                return arr;
            },
            enumerable: true,
        });
    } catch(e) { /* navigator.plugins 不可配置，跳过 */ }
    try {
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => ({ length: 0, item: () => null, namedItem: () => null }),
        });
    } catch(e) { /* navigator.mimeTypes 不可配置，跳过 */ }

    // ── A4. 语言 / 平台 ─────────────────────────────────────────────────
    try { Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] }); } catch(e) {}
    try { Object.defineProperty(navigator, 'platform',  { get: () => 'Win32' }); } catch(e) {}

    // ── A5. Permissions API 修复 ────────────────────────────────────────
    if (navigator.permissions && navigator.permissions.query) {
        const _origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (params) => {
            if (params && params.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission, onchange: null });
            }
            return _origQuery(params);
        };
    }

    // ── A6. Canvas 指纹扰动 ────────────────────────────────────────────
    const _origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
        const ctx = _origGetContext.apply(this, [type, ...args]);
        if ((type === '2d') && ctx && !this.__stealthPatched) {
            this.__stealthPatched = true;
            const _origFillText = ctx.fillText.bind(ctx);
            ctx.fillText = function(text, x, y, ...rest) {
                const dx = (Math.random() - 0.5) * 0.6;
                const dy = (Math.random() - 0.5) * 0.6;
                return _origFillText(text, x + dx, y + dy, ...rest);
            };
        }
        return ctx;
    };

    const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        try {
            const ctx2d = _origGetContext.call(this, '2d');
            if (ctx2d) {
                const imageData = ctx2d.getImageData(0, 0, 1, 1);
                imageData.data[3] = Math.max(0, Math.min(255, imageData.data[3] + (Math.random() > 0.5 ? 1 : -1)));
                ctx2d.putImageData(imageData, 0, 0);
            }
        } catch (_) {}
        return _origToDataURL.apply(this, args);
    };

    // ── A7. WebGL 指纹伪装 ─────────────────────────────────────────────
    const _patchWebGL = (GL) => {
        if (!GL) return;
        const _origGetParam = GL.prototype.getParameter;
        GL.prototype.getParameter = function(parameter) {
            const VENDOR   = 0x1F00;
            const RENDERER = 0x1F01;
            const UNMASKED_VENDOR   = 0x9245;
            const UNMASKED_RENDERER = 0x9246;
            switch (parameter) {
                case VENDOR:          return 'Intel Inc.';
                case RENDERER:        return 'Intel Iris OpenGL Engine';
                case UNMASKED_VENDOR: return 'Intel Inc.';
                case UNMASKED_RENDERER: return 'Intel Iris OpenGL Engine';
                default: return _origGetParam.apply(this, arguments);
            }
        };
    };
    _patchWebGL(window.WebGLRenderingContext);
    _patchWebGL(window.WebGL2RenderingContext);

    // ── A8. AudioContext 指纹扰动 ──────────────────────────────────────
    if (window.AudioContext || window.webkitAudioContext) {
        const _AudioCtx = window.AudioContext || window.webkitAudioContext;
        const _origCreateOscillator = _AudioCtx.prototype.createOscillator;
        _AudioCtx.prototype.createOscillator = function() {
            const osc = _origCreateOscillator.apply(this, arguments);
            const _origStart = osc.start.bind(osc);
            osc.start = function(when) {
                if (osc.frequency && osc.frequency.value) {
                    osc.frequency.value += (Math.random() - 0.5) * 0.002;
                }
                return _origStart(when);
            };
            return osc;
        };
    }

    // ── A9. 字体枚举保护 ───────────────────────────────────────────────
    if (document.fonts && document.fonts.check) {
        const _origFontsCheck = document.fonts.check.bind(document.fonts);
        document.fonts.check = function(font, text) {
            const rareFont = /(wingdings|marlett|symbol|webdings)/i.test(font);
            if (rareFont) return false;
            return _origFontsCheck(font, text);
        };
    }

    // ── A10. Timezone 一致性保护 ───────────────────────────────────────
    const _origResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
    Intl.DateTimeFormat.prototype.resolvedOptions = function() {
        const opts = _origResolvedOptions.call(this);
        opts.timeZone = 'Asia/Shanghai';
        return opts;
    };

    // ── A11. 清除 Playwright 痕迹 ─────────────────────────────────────
    delete window.__playwright;
    delete window.__pw_manual;
    delete window.__PW_inspect;
    delete window.playwright;
    delete window._playwrightRunner;

    // ── A12. navigator.connection 补全 ─────────────────────────────────
    if (!navigator.connection) {
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false,
            }),
        });
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  Part B: 页面离开保护（阻断鼠标移出/失焦/可见性检测）
    // ═══════════════════════════════════════════════════════════════════════

    // ── B1. 阻断鼠标离开/指针离开检测 ──────────────────────────────────
    document.addEventListener('mouseleave', function(e) {
        e.stopImmediatePropagation();
        e.preventDefault();
    }, true);
    document.addEventListener('pointerleave', function(e) {
        e.stopImmediatePropagation();
        e.preventDefault();
    }, true);

    document.addEventListener('mouseout', function(e) {
        if (!e.relatedTarget || e.relatedTarget.nodeName === 'HTML') {
            e.stopImmediatePropagation();
            e.preventDefault();
        }
    }, true);
    document.addEventListener('pointerout', function(e) {
        if (!e.relatedTarget || e.relatedTarget.nodeName === 'HTML') {
            e.stopImmediatePropagation();
            e.preventDefault();
        }
    }, true);

    window.addEventListener('mouseleave', function(e) {
        e.stopImmediatePropagation();
        e.preventDefault();
    }, true);
    window.addEventListener('mouseout', function(e) {
        if (!e.relatedTarget || e.relatedTarget.nodeName === 'HTML') {
            e.stopImmediatePropagation();
            e.preventDefault();
        }
    }, true);

    // ── B2. 阻断失焦/可见性变化检测 ────────────────────────────────────
    document.addEventListener('visibilitychange', function(e) {
        e.stopImmediatePropagation();
    }, true);
    document.addEventListener('blur', function(e) {
        e.stopImmediatePropagation();
    }, true);
    window.addEventListener('blur', function(e) {
        e.stopImmediatePropagation();
    }, true);

    // ── B3. 伪造 hasFocus / visibilityState（定时器轮询检测）─────────
    document.hasFocus = function() { return true; };
    try {
        Object.defineProperty(Document.prototype, 'hidden', {
            get: function() { return false; },
            configurable: true,
        });
    } catch(e) { /* 原生属性不可配置 */ }
    try {
        Object.defineProperty(Document.prototype, 'visibilityState', {
            get: function() { return 'visible'; },
            configurable: true,
        });
    } catch(e) { /* 原生属性不可配置 */ }

    // ── B4. 阻止 onbeforeunload 弹窗 ───────────────────────────────────
    window.addEventListener('beforeunload', function(e) { e.preventDefault(); }, true);

    console.log('[Stealth] Anti-detection script loaded (fingerprint + minimal block)');
})();
