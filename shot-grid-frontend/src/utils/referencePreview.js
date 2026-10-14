export function referenceKind(file) {
  const ext = String(file?.originalName || '').split('.').pop().toLowerCase()
  if (['bmp', 'gif', 'jpg', 'jpeg', 'png', 'webp'].includes(ext)) return 'image'
  if (['mp4', 'mov', 'webm'].includes(ext)) return 'video'
  if (['pdf', 'docx', 'xlsx', 'pptx', 'txt'].includes(ext)) return ext
  return 'unsupported'
}

export function referenceBlob(blob, file) {
  const ext = String(file?.originalName || '').split('.').pop().toLowerCase()
  const types = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', bmp: 'image/bmp', gif: 'image/gif', webp: 'image/webp', mp4: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm', pdf: 'application/pdf' }
  return new Blob([blob], { type: types[ext] || blob.type })
}

export async function readReferenceDocument(blob, kind) {
  if (blob.size > 20 * 1024 * 1024) throw new Error('文件超过 20 MiB，请下载查看')
  const buffer = await blob.arrayBuffer()
  if (kind === 'txt') {
    try { return { text: new TextDecoder('utf-8', { fatal: true }).decode(buffer) } }
    catch { return { text: new TextDecoder('gb18030').decode(buffer) } }
  }
  if (kind === 'docx') {
    const [{ default: mammoth }, { default: DOMPurify }] = await Promise.all([
      import('mammoth/mammoth.browser'), import('dompurify')
    ])
    const { value } = await mammoth.convertToHtml({ arrayBuffer: buffer }, { externalFileAccess: false })
    const html = DOMPurify.sanitize(value, { FORBID_TAGS: ['style', 'form', 'input', 'button'], FORBID_ATTR: ['style', 'href', 'srcset'] })
    return { html: `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><style>body{font:16px/1.8 system-ui;margin:28px;color:#222;background:white;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style></head><body>${html}</body></html>` }
  }
  if (kind === 'xlsx') {
    const { default: ExcelJS } = await import('exceljs')
    const workbook = new ExcelJS.Workbook()
    await workbook.xlsx.load(buffer)
    return { sheets: workbook.worksheets.map(sheet => ({
      name: sheet.name,
      truncated: sheet.rowCount > 1000 || sheet.columnCount > 100,
      columns: Array.from({ length: Math.min(sheet.columnCount, 100) }, (_, i) => ({ key: String(i), label: sheet.getColumn(i + 1).letter })),
      rows: Array.from({ length: Math.min(sheet.rowCount, 1000) }, (_, rowIndex) => {
        const row = sheet.getRow(rowIndex + 1)
        return { rowNumber: rowIndex + 1, ...Object.fromEntries(Array.from({ length: Math.min(sheet.columnCount, 100) }, (_, i) => [String(i), row.getCell(i + 1).text])) }
      })
    })) }
  }
  if (kind === 'pptx') {
    const { default: JSZip } = await import('jszip')
    const zip = await JSZip.loadAsync(buffer)
    const parseXml = text => new DOMParser().parseFromString(text, 'application/xml')
    const presentation = zip.file('ppt/presentation.xml')
    const relationships = zip.file('ppt/_rels/presentation.xml.rels')
    if (!presentation || !relationships) throw new Error('幻灯片目录缺失')
    const relationshipXml = parseXml(await relationships.async('string'))
    const slideTargets = new Map(Array.from(relationshipXml.getElementsByTagNameNS('*', 'Relationship'))
      .filter(item => item.getAttribute('Type')?.endsWith('/slide') && item.getAttribute('TargetMode') !== 'External')
      .map(item => [item.getAttribute('Id'), item.getAttribute('Target')]))
    const slideXml = parseXml(await presentation.async('string'))
    // 幻灯片文件名不代表播放顺序，必须按演示文稿的关系目录读取。
    const slides = Array.from(slideXml.getElementsByTagNameNS('*', 'sldId')).map(item => {
      const id = item.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id')
      const target = slideTargets.get(id)
      if (!/^slides\/slide\d+\.xml$/.test(target || '')) throw new Error('幻灯片引用无效')
      return `ppt/${target}`
    })
    const pages = []
    for (const name of slides) {
      const xml = parseXml(await zip.file(name).async('string'))
      pages.push(Array.from(xml.getElementsByTagNameNS('*', 'p')).map(p => Array.from(p.getElementsByTagNameNS('*', 't')).map(t => t.textContent).join('')).join('\n'))
    }
    return { pages }
  }
  throw new Error('该格式暂不支持在线预览，请下载查看')
}
