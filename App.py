import streamlit as st
import requests
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from ebooklib import epub
import textwrap

# --- CONSTANTS & CONFIG ---
st.set_page_config(page_title="Substack to Kindle", layout="centered")

# --- LOGIC: SUBSTACK API SCRAPER ---

def extract_slug(url):
    """Extracts the post slug from a standard Substack URL."""
    # Example: https://read.substack.com/p/welcome-to-substack -> welcome-to-substack
    try:
        if "/p/" in url:
            return url.split("/p/")[1].split("/")[0].split("?")[0]
        return None
    except:
        return None

def get_substack_api_data(url):
    """
    Uses Substack's internal API to fetch data without parsing HTML.
    """
    slug = extract_slug(url)
    if not slug:
        return None, "Invalid Substack URL. Must contain '/p/'."

    # Subdomain logic (e.g., 'https://lenny.substack.com' -> 'lenny')
    try:
        domain = url.split("//")[1].split("/")[0]
    except:
        return None, "Could not parse domain."

    # 1. Get Post Metadata
    api_url = f"https://{domain}/api/v1/posts/{slug}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        resp = requests.get(api_url, headers=headers)
        if resp.status_code != 200:
            return None, f"API Error: {resp.status_code}"
        
        data = resp.json()
        post_id = data.get("id")
        title = data.get("title", "Untitled")
        author = data.get("publishedBylines", [{}])[0].get("name", "Unknown Author")
        date_iso = data.get("post_date")
        date_str = datetime.fromisoformat(date_iso.replace("Z", "+00:00")).strftime("%B %d, %Y") if date_iso else "Undated"
        body_html = data.get("body_html", "")
        
        # 2. Get Comments (Public API)
        comments = []
        if post_id:
            comment_url = f"https://{domain}/api/v1/posts/{post_id}/comments?sort=newest"
            c_resp = requests.get(comment_url, headers=headers)
            if c_resp.status_code == 200:
                c_data = c_resp.json()
                # Extract text from comments
                for c in c_data.get("comments", []):
                    # We grab the raw text content if available
                    c_body = c.get("body", "")
                    c_user = c.get("name", "Anonymous")
                    if c_body:
                        comments.append(f"<b>{c_user}:</b> {c_body}")
        
        return {
            "title": title,
            "author": author,
            "date": date_str,
            "body": body_html,
            "comments": comments,
            "url": url,
            "domain": domain
        }, None

    except Exception as e:
        return None, str(e)

# --- LOGIC: COVER GENERATOR (3 STYLES) ---

def draw_text_wrapped(draw, text, x, y, max_width, font, fill):
    """Helper to wrap text on image."""
    lines = textwrap.wrap(text, width=max_width) # approx char width
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += 40 # Line height
    return current_y

def generate_cover(style, data):
    width, height = 600, 900
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Load Font (Fallback to default if custom not found)
    try:
        # In Streamlit Cloud, usually DejavuSans is available or we use default
        # For better results in cloud, we use large default size or upload a ttf
        font_large = ImageFont.load_default() 
        font_small = ImageFont.load_default()
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    if style == "Classic Typography":
        # Cream background, dark text, centered
        img = Image.new('RGB', (width, height), color=(248, 241, 229))
        d = ImageDraw.Draw(img)
        d.rectangle([20, 20, width-20, height-20], outline=(0,0,0), width=3)
        
        # Title
        d.text((50, 200), data['title'], fill="black", font=font_large)
        d.text((50, 400), data['author'], fill="black", font=font_small)
        d.text((50, 450), data['date'], fill="gray", font=font_small)
        d.text((50, height-100), "SUBSTACK ARCHIVE", fill="gray", font=font_small)

    elif style == "Modern Dark":
        # Black background, White text, Bold accent
        img = Image.new('RGB', (width, height), color=(20, 20, 20))
        d = ImageDraw.Draw(img)
        
        # Accent Line
        d.rectangle([0, 150, 20, 150 + 200], fill=(255, 87, 34)) # Orange strip
        
        d.text((50, 150), data['title'], fill="white", font=font_large)
        d.text((50, 500), f"Written by {data['author']}", fill="lightgray", font=font_small)
        d.text((50, 530), data['date'], fill="gray", font=font_small)

    elif style == "Minimalist White":
        # Pure white, very clean, bottom aligned
        img = Image.new('RGB', (width, height), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        
        d.text((50, 50), "ARTICLE", fill="red", font=font_small)
        d.text((50, 100), data['title'], fill="black", font=font_large)
        d.line((50, 300, 550, 300), fill="black", width=2)
        d.text((50, 320), data['author'].upper(), fill="black", font=font_small)
        d.text((50, height-50), data['domain'], fill="gray", font=font_small)

    # Convert to bytes
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="JPEG")
    return img_buffer.getvalue()

# --- LOGIC: EPUB CREATION ---

def create_epub(data, cover_bytes):
    book = epub.EpubBook()
    book.set_identifier(data['url'])
    book.set_title(data['title'])
    book.set_language('en')
    book.add_author(data['author'])
    
    book.set_cover("cover.jpg", cover_bytes)
    
    # Intro Chapter
    intro_html = f"""
    <h1>{data['title']}</h1>
    <h3>{data['author']}</h3>
    <p><i>{data['date']}</i></p>
    <p>Source: <a href="{data['url']}">{data['url']}</a></p>
    <hr/>
    """
    
    # Combine body
    final_html = intro_html + data['body']
    
    # Add Comments Chapter if exists
    if data['comments']:
        final_html += "<hr/><h1>Comments</h1>"
        for c in data['comments']:
            final_html += f"<div style='margin-bottom:15px; border-left:2px solid #ccc; padding-left:10px;'>{c}</div>"

    c1 = epub.EpubHtml(title='Article', file_name='article.xhtml', lang='en')
    c1.content = final_html
    book.add_item(c1)
    
    book.toc = (c1,)
    book.spine = ['nav', c1]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    buffer = io.BytesIO()
    epub.write_epub(buffer, book, {})
    return buffer

# --- UI: MAIN INTERFACE ---

st.title("Ray's Substack Reader")
st.markdown("Paste a Substack link. Get a Kindle file with comments.")

url_input = st.text_input("Substack URL", placeholder="https://...")

if url_input:
    if st.button("Fetch Article"):
        with st.spinner("Talking to Substack API..."):
            data, error = get_substack_api_data(url_input)
            
            if error:
                st.error(error)
            else:
                st.session_state['data'] = data
                st.success("Article & Comments Found!")

if 'data' in st.session_state:
    data = st.session_state['data']
    
    st.divider()
    st.subheader("Select a Cover Style")
    
    # Generate 3 options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.caption("Classic")
        cov1 = generate_cover("Classic Typography", data)
        st.image(cov1)
        if st.button("Select Classic", key="btn1"):
            st.session_state['selected_cover'] = cov1
            
    with col2:
        st.caption("Dark")
        cov2 = generate_cover("Modern Dark", data)
        st.image(cov2)
        if st.button("Select Dark", key="btn2"):
            st.session_state['selected_cover'] = cov2
            
    with col3:
        st.caption("Minimal")
        cov3 = generate_cover("Minimalist White", data)
        st.image(cov3)
        if st.button("Select Minimal", key="btn3"):
            st.session_state['selected_cover'] = cov3

    if 'selected_cover' in st.session_state:
        st.divider()
        st.write(f"**Ready to Download:** {data['title']}")
        st.write(f"**Comments included:** {len(data['comments'])}")
        
        epub_file = create_epub(data, st.session_state['selected_cover'])
        
        st.download_button(
            label="Download EPUB for Kindle",
            data=epub_file.getvalue(),
            file_name=f"{data['title'][:15]}_Kindle.epub",
            mime="application/epub+zip"
        )
