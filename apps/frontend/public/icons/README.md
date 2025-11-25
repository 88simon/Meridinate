# Custom Icons

This directory contains custom PNG icons used throughout the Meridinate frontend.

## Structure

- **Root (`/icons/`)**: General-purpose icons
- **`/icons/tokens/`**: Token-specific icons (e.g., bunny_icon.png for token branding)
- **`/icons/ui/`**: UI element icons (buttons, indicators, etc.)

## Naming Conventions

- Use lowercase with underscores: `bunny_icon.png`
- Be descriptive: `token_verified_badge.png` instead of `badge1.png`
- Include size in name if multiple sizes exist: `logo_small.png`, `logo_large.png`

## Usage in Components

Import icons using the `/icons/` path from the public directory:

```tsx
import Image from 'next/image';

// Example usage
<Image
  src="/icons/bunny_icon.png"
  alt="Bunny Token"
  width={24}
  height={24}
/>
```

Or for background images in CSS:
```css
background-image: url('/icons/bunny_icon.png');
```

## File Format

- **PNG** - Preferred format for custom icons with transparency
- Recommended: Use PNG-24 with alpha channel for best quality
- Optimize PNGs before adding (use tools like TinyPNG or ImageOptim)
