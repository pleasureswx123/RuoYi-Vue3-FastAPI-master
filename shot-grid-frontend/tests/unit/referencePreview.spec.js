import { Blob as NodeBlob } from 'node:buffer'
import { expect, it } from 'vitest'
import JSZip from 'jszip'
import ExcelJS from 'exceljs'
import { readReferenceDocument } from '@/utils/referencePreview'

it('DOCX 真实解析正文和表格并隔离活动链接', async () => {
  const zip = new JSZip()
  zip.file('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
  zip.file('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
  zip.file('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>项目剧本内容</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>镜头表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
  const bytes = await zip.generateAsync({ type: 'uint8array' })
  const blob = new Blob([bytes])
  const buffer = await new Promise(resolve => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.readAsArrayBuffer(blob)
  })
  const result = await readReferenceDocument({ size: blob.size, arrayBuffer: async () => buffer }, 'docx')
  expect(result.html).toContain('项目剧本内容')
  expect(result.html).toContain('镜头表格')
  expect(result.html).toContain("default-src 'none'")
})

it('XLSX 读取多个工作表、文字及公式缓存值', async () => {
  const workbook = new ExcelJS.Workbook()
  const sheet = workbook.addWorksheet('制作安排')
  sheet.addRow(['镜头', '时长'])
  sheet.addRow(['0010', { formula: '2+3', result: 5 }])
  workbook.addWorksheet('空表')
  const result = await readReferenceDocument(new NodeBlob([await workbook.xlsx.writeBuffer()]), 'xlsx')
  expect(result.sheets.map(item => item.name)).toEqual(['制作安排', '空表'])
  expect(result.sheets[0].rows[1]).toMatchObject({ 0: '0010', 1: '5' })
})

it('TXT 内容保持纯文本，PPTX 按页提取文字', async () => {
  expect(await readReferenceDocument(new NodeBlob(['<script>示例</script>']), 'txt')).toEqual({ text: '<script>示例</script>' })
  const zip = new JSZip()
  zip.file('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="1" r:id="rId1"/></p:sldIdLst></p:presentation>')
  zip.file('ppt/_rels/presentation.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>')
  zip.file('ppt/slides/slide1.xml', '<a:root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>分镜说明</a:t></a:r></a:p></a:root>')
  const result = await readReferenceDocument(new NodeBlob([await zip.generateAsync({ type: 'uint8array' })]), 'pptx')
  expect(result.pages).toEqual(['分镜说明'])
})
