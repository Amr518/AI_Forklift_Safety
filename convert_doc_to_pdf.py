import sys
import os
import re
import markdown
import weasyprint

def main():
    md_path = "/home/forklift/Desktop/AI_Forklift_Safety/PROJECT_FULL_DOCUMENTATION.md"
    pdf_path = "/home/forklift/Desktop/AI_Forklift_Safety/PROJECT_FULL_DOCUMENTATION.pdf"
    
    print(f"Reading markdown from: {md_path}")
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # Convert markdown to HTML with necessary extensions
    extensions = [
        'tables',
        'fenced_code',
        'sane_lists',
        'def_list'
    ]
    html_body = markdown.markdown(md_text, extensions=extensions)

    # Wrap in styled HTML
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Limitless Future — AI Forklift Safety System Documentation</title>
<style>
    @page {{
        size: A4;
        margin: 22mm 16mm 22mm 16mm;
        @top-left {{
            content: "Limitless Future — AI Forklift Safety System";
            font-family: 'Liberation Sans', 'DejaVu Sans', sans-serif;
            font-size: 7.5pt;
            color: #64748b;
            border-bottom: 0.5pt solid #cbd5e1;
            padding-bottom: 4px;
        }}
        @top-right {{
            content: "Technical Reference Manual";
            font-family: 'Liberation Sans', 'DejaVu Sans', sans-serif;
            font-size: 7.5pt;
            color: #64748b;
            border-bottom: 0.5pt solid #cbd5e1;
            padding-bottom: 4px;
        }}
        @bottom-left {{
            content: "Ubuntu 24.04 LTS — Production Release";
            font-family: 'Liberation Sans', 'DejaVu Sans', sans-serif;
            font-size: 7.5pt;
            color: #64748b;
            border-top: 0.5pt solid #cbd5e1;
            padding-top: 4px;
        }}
        @bottom-right {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: 'Liberation Sans', 'DejaVu Sans', sans-serif;
            font-size: 7.5pt;
            font-weight: bold;
            color: #334155;
            border-top: 0.5pt solid #cbd5e1;
            padding-top: 4px;
        }}
    }}

    body {{
        font-family: 'Liberation Sans', 'DejaVu Sans', 'Segoe UI', Arial, sans-serif;
        font-size: 9pt;
        line-height: 1.55;
        color: #1e293b;
    }}

    h1 {{
        font-size: 19pt;
        color: #0f172a;
        border-bottom: 2pt solid #2563eb;
        padding-bottom: 5px;
        margin-top: 26pt;
        margin-bottom: 12pt;
        page-break-after: avoid;
    }}

    h2 {{
        font-size: 14pt;
        color: #1e3a8a;
        border-bottom: 1pt solid #93c5fd;
        padding-bottom: 4px;
        margin-top: 20pt;
        margin-bottom: 8pt;
        page-break-after: avoid;
    }}

    h3 {{
        font-size: 11.5pt;
        color: #1d4ed8;
        margin-top: 14pt;
        margin-bottom: 6pt;
        page-break-after: avoid;
    }}

    h4 {{
        font-size: 10pt;
        color: #334155;
        margin-top: 10pt;
        margin-bottom: 4pt;
        page-break-after: avoid;
    }}

    p {{
        margin-top: 4pt;
        margin-bottom: 7pt;
    }}

    /* Tables styling */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 10pt 0;
        font-size: 8pt;
        page-break-inside: auto;
    }}

    tr {{
        page-break-inside: avoid;
        page-break-after: auto;
    }}

    th {{
        background-color: #1e3a8a;
        color: #ffffff;
        text-align: left;
        padding: 5pt 7pt;
        font-weight: 600;
        border: 0.5pt solid #1e3a8a;
    }}

    td {{
        padding: 4.5pt 7pt;
        border: 0.5pt solid #cbd5e1;
        vertical-align: top;
    }}

    tr:nth-child(even) {{
        background-color: #f8fafc;
    }}

    /* Code & ASCII blocks */
    pre {{
        background-color: #0f172a;
        color: #e2e8f0;
        padding: 8pt 10pt;
        border-radius: 4px;
        font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace;
        font-size: 7.2pt;
        line-height: 1.35;
        overflow-x: hidden;
        white-space: pre-wrap;
        word-break: break-word;
        page-break-inside: avoid;
        margin: 8pt 0;
        border: 1pt solid #1e293b;
    }}

    code {{
        font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace;
        font-size: 8pt;
        background-color: #f1f5f9;
        color: #b91c1c;
        padding: 1pt 3pt;
        border-radius: 3px;
        border: 0.5pt solid #e2e8f0;
    }}

    pre code {{
        background-color: transparent;
        color: inherit;
        padding: 0;
        border: none;
        font-size: inherit;
    }}

    /* Blockquotes and Callouts */
    blockquote {{
        border-left: 3.5pt solid #2563eb;
        background-color: #eff6ff;
        margin: 8pt 0;
        padding: 6pt 10pt;
        color: #1e3a8a;
        font-size: 8.5pt;
        border-radius: 0 4px 4px 0;
        page-break-inside: avoid;
    }}

    ul, ol {{
        margin-top: 3pt;
        margin-bottom: 7pt;
        padding-left: 18pt;
    }}

    li {{
        margin-bottom: 2pt;
    }}

    hr {{
        border: none;
        border-top: 1pt solid #cbd5e1;
        margin: 16pt 0;
    }}

    a {{
        color: #2563eb;
        text-decoration: none;
    }}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""

    print("Rendering HTML with WeasyPrint...")
    html = weasyprint.HTML(string=html_doc, base_url="/home/forklift/Desktop/AI_Forklift_Safety")
    print(f"Generating PDF: {pdf_path} ... (this may take a few moments for 3,500+ lines)")
    html.write_pdf(pdf_path)
    print(f"SUCCESS! Generated PDF: {pdf_path}")
    print(f"File size: {os.path.getsize(pdf_path) / (1024*1024):.2f} MB")

if __name__ == "__main__":
    main()
