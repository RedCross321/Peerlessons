// Подключает воркеры Monaco через нативный механизм Vite (?worker).
// TS/JSON-воркеры намеренно не подключаются: комнаты работают только с
// HTML/CSS/JS, а ts.worker весит около 7 МБ и не нужен для базового JS.
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import CssWorker from 'monaco-editor/language/css/css.worker.js?worker'
import HtmlWorker from 'monaco-editor/language/html/html.worker.js?worker'

self.MonacoEnvironment = {
  getWorker(_workerId, label) {
    switch (label) {
      case 'css':
      case 'scss':
      case 'less':
        return new CssWorker()
      case 'html':
      case 'handlebars':
      case 'razor':
        return new HtmlWorker()
      default:
        return new EditorWorker()
    }
  },
}
