(function () {
  var MODE = 'capture';

  function pathOf(element) {
    var parts = [];
    var node = element;
    while (node && node.nodeType === 1 && node.parentNode) {
      var index = Array.prototype.indexOf.call(node.parentNode.children, node);
      if (index < 0) return '';
      parts.unshift(index);
      node = node.parentNode;
    }
    return parts.join('/');
  }

  function elementAt(path) {
    var node = document.documentElement;
    if (!path) return node;
    var parts = path.split('/');
    for (var i = 0; i < parts.length; i += 1) {
      node = node && node.children ? node.children[Number(parts[i])] : null;
      if (!node) return null;
    }
    return node;
  }

  function post(payload) {
    payload.source = 'peerlessons-preview';
    try {
      window.parent.postMessage(payload, '*');
    } catch (error) {
      /* родитель недоступен */
    }
  }

  function sendInteraction(detail) {
    post({ action: 'interaction', event: detail });
  }

  if (MODE === 'capture') {
    document.addEventListener('click', function (event) {
      if (!event.isTrusted) return;
      var target = event.target;
      if (!target || target.nodeType !== 1) return;

      var tag = target.tagName;
      if (tag === 'SELECT' || tag === 'TEXTAREA') return;
      if (tag === 'INPUT') {
        var inputType = String(target.type || '').toLowerCase();
        if (
          ['button', 'submit', 'reset', 'image'].indexOf(inputType) === -1
        ) {
          return;
        }
      }

      sendInteraction({ action: 'click', path: pathOf(target) });
    }, true);

    document.addEventListener('input', function (event) {
      if (!event.isTrusted) return;
      var target = event.target;
      if (!target || target.nodeType !== 1) return;

      var detail = { action: 'input', path: pathOf(target) };
      if (typeof target.value === 'string') {
        detail.value = target.value.slice(0, 2000);
      } else if (target.isContentEditable) {
        detail.value = String(target.textContent || '').slice(0, 2000);
      }
      if (typeof target.checked === 'boolean') detail.checked = target.checked;

      sendInteraction(detail);
    }, true);

    document.addEventListener('change', function (event) {
      if (!event.isTrusted) return;
      var target = event.target;
      if (!target || target.nodeType !== 1) return;

      var detail = { action: 'change', path: pathOf(target) };
      if (typeof target.value === 'string') detail.value = target.value;
      if (typeof target.checked === 'boolean') detail.checked = target.checked;

      sendInteraction(detail);
    }, true);

    ['keydown', 'keyup'].forEach(function (type) {
      document.addEventListener(type, function (event) {
        if (!event.isTrusted) return;
        var target = event.target;
        sendInteraction({
          action: type,
          path: target && target.nodeType === 1 ? pathOf(target) : '',
          key: event.key,
          code: event.code,
          altKey: event.altKey,
          ctrlKey: event.ctrlKey,
          metaKey: event.metaKey,
          shiftKey: event.shiftKey
        });
      }, true);
    });
  }

  if (MODE === 'capture' || MODE === 'replay') {
    window.addEventListener('message', function (event) {
      var data = event.data;
      if (!data || data.source !== 'peerlessons-preview') return;
      if (data.action !== 'replay' || !data.event) return;

      var detail = data.event;
      var target = elementAt(detail.path || '');
      if (!target) return;

      if (detail.action === 'click') {
        target.click();
        return;
      }

      if (detail.action === 'input' || detail.action === 'change') {
        if (detail.checked !== undefined && 'checked' in target) {
          target.checked = Boolean(detail.checked);
        } else if (detail.value !== undefined) {
          if (target.isContentEditable) {
            target.textContent = detail.value;
          } else {
            target.value = detail.value;
          }
        }

        var kind = detail.action === 'input' ? 'input' : 'change';
        target.dispatchEvent(new Event(kind, { bubbles: true }));
        return;
      }

      if (detail.action === 'keydown' || detail.action === 'keyup') {
        try {
          target.focus();
        } catch (error) {
          /* элемент может быть нефокусируемым */
        }

        target.dispatchEvent(
          new KeyboardEvent(detail.action, {
            key: detail.key,
            code: detail.code,
            altKey: Boolean(detail.altKey),
            ctrlKey: Boolean(detail.ctrlKey),
            metaKey: Boolean(detail.metaKey),
            shiftKey: Boolean(detail.shiftKey),
            bubbles: true,
            cancelable: true
          })
        );
      }
    });
  }

  post({ action: 'ready' });
})();