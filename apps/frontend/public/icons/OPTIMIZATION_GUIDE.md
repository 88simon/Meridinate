# Icon Optimization Guide

## Current Status

**bunny_icon.png**: 1.3 MB (UNOPTIMIZED)

This file is extremely large for a small icon and will impact page load performance. While Next.js Image component provides automatic optimization at runtime, optimizing the source file provides additional benefits:

- Faster initial builds
- Reduced storage/bandwidth in development
- Better performance baseline

## Recommended Optimization

### Goal

Reduce bunny_icon.png from **1.3 MB** to **<100 KB** (90%+ reduction)

### Option 1: Online Tools (Easiest)

**TinyPNG** (https://tinypng.com/)

1. Visit https://tinypng.com/
2. Upload bunny_icon.png
3. Download optimized version
4. Replace original file
5. Expected result: 70-80% size reduction with no visible quality loss

**ImageOptim** (https://imageoptim.com/) - macOS only

1. Download ImageOptim app
2. Drag bunny_icon.png into app
3. App automatically optimizes and replaces file
4. Expected result: 60-80% size reduction

### Option 2: Command Line Tools

**Using pngquant** (lossy compression, best results):

```bash
# Install pngquant
# Windows (via chocolatey): choco install pngquant
# macOS: brew install pngquant
# Linux: apt-get install pngquant

# Optimize (80% quality, typically 70-90% smaller)
cd apps/frontend/public/icons/tokens
pngquant --quality=80-90 bunny_icon.png --output bunny_icon_optimized.png
mv bunny_icon_optimized.png bunny_icon.png
```

**Using OptiPNG** (lossless compression, moderate results):

```bash
# Install optipng
# Windows (via chocolatey): choco install optipng
# macOS: brew install optipng
# Linux: apt-get install optipng

# Optimize (lossless, typically 10-30% smaller)
cd apps/frontend/public/icons/tokens
optipng -o7 bunny_icon.png
```

### Option 3: Convert to SVG (Best Performance)

If the bunny icon is vector-based or has simple shapes, converting to SVG would be ideal:

**Benefits:**

- 10-100x smaller file size (typically 2-10 KB)
- Resolution-independent (scales perfectly to any size)
- No pixelation at high DPI displays
- Can be styled with CSS

**Tools:**

- Adobe Illustrator (Image Trace)
- Inkscape (free) - Trace Bitmap feature
- Online: Vectorizer.io, SVGator

**Implementation:**

```tsx
// Replace Image component with inline SVG
<svg className='h-6 w-6' viewBox='0 0 24 24' fill='currentColor'>
  <path d='...' />
</svg>
```

## Verification

After optimization, verify file size:

**Windows:**

```cmd
dir bunny_icon.png
```

**Unix/macOS:**

```bash
ls -lh bunny_icon.png
```

**Target:** <100 KB (ideally <50 KB)

## Current Implementation

The bunny icon is already using Next.js Image component which provides:

- ✅ Automatic WebP/AVIF conversion
- ✅ Responsive sizing
- ✅ Lazy loading
- ✅ On-demand optimization

However, optimizing the source PNG will:

- ✅ Reduce development server load
- ✅ Faster Next.js builds
- ✅ Lower baseline bandwidth usage

## Locations

bunny_icon.png is used in:

1. Multi-Token Early Wallets section title - [page.tsx:1992-1998](../src/app/dashboard/tokens/page.tsx#L1992-L1998)
2. Token Table "View Details" button - [tokens-table.tsx:481-487](../src/app/dashboard/tokens/tokens-table.tsx#L481-L487)

Both use Next.js Image component with proper width/height attributes for optimal performance.
