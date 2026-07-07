import { marked } from 'marked'
import katex from 'katex'
import 'katex/dist/katex.min.css'

marked.setOptions({
  breaks: true,
  gfm: true,
})

/**
 * 把含 Markdown + LaTeX（$...$ 行内 / $$...$$ 块级）的文本渲染为 HTML 字符串。
 * 供智能问答、学术搜索综述等多处复用。
 */
export function renderContent(text) {
  if (!text) return ''

  let html = marked.parse(text)

  html = html.replace(/\$\$(.+?)\$\$/g, (match, formula) => {
    try {
      return katex.renderToString(formula.trim(), {
        throwOnError: false,
        displayMode: true,
      })
    } catch {
      return `<code>${formula}</code>`
    }
  })

  html = html.replace(/\$(.+?)\$/g, (match, formula) => {
    try {
      return katex.renderToString(formula.trim(), {
        throwOnError: false,
        displayMode: false,
      })
    } catch {
      return `<code>${formula}</code>`
    }
  })

  return html
}
