/**
 * recorder.js - 操作录制脚本
 * ============================================================
 * 监听用户的 click/input/navigate，通过 console.log 发送记录。
 * 由 ActionRecorder 消费 __RECORD__ 前缀的 console 消息。
 */
(function() {
    if (window.__recorder_injected__) return;
    window.__recorder_injected__ = true;

    function getSelector(el) {
        if (!el || el === document.body) return 'body';
        if (el.id) return '#' + el.id;
        if (el.name) return '[name="' + el.name + '"]';
        var root = el.getRootNode ? el.getRootNode() : document;
        var path = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            path += '.' + el.className.trim().split(/\s+/).join('.');
        }
        var parent = el.parentElement;
        if (parent) {
            var siblings = Array.from(parent.children).filter(function(c) {
                return c.tagName === el.tagName;
            });
            if (siblings.length > 1) {
                path += ':nth-child(' + (siblings.indexOf(el) + 1) + ')';
            }
        }
        if (root !== document) {
            var host = root.host;
            if (host) {
                path = getSelector(host) + ' >>> ' + path;
            }
        }
        return path;
    }

    function emit(action, data) {
        console.log('__RECORD__:' + JSON.stringify(Object.assign({action: action, ts: Date.now()}, data)));
    }

    document.addEventListener('click', function(e) {
        var el = e.target;
        emit('click', {
            selector: getSelector(el),
            tag: el.tagName,
            text: (el.innerText || el.value || '').trim().slice(0, 80),
            href: el.href || '',
            x: e.clientX, y: e.clientY
        });
    }, true);

    document.addEventListener('change', function(e) {
        var el = e.target;
        if (['INPUT','SELECT','TEXTAREA'].indexOf(el.tagName) !== -1) {
            emit('input', {
                selector: getSelector(el),
                tag: el.tagName,
                type: el.type || '',
                value: el.type === 'password' ? '***' : (el.value || '').slice(0, 200)
            });
        }
    }, true);

    var _push = history.pushState.bind(history);
    history.pushState = function(s, t, url) {
        _push(s, t, url);
        emit('navigate', {url: location.href});
    };
    var _replace = history.replaceState.bind(history);
    history.replaceState = function(s, t, url) {
        _replace(s, t, url);
        emit('navigate', {url: location.href});
    };

    emit('pageload', {url: location.href, title: document.title || ''});
})();
