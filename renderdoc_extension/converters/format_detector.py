"""
Texture format detection and parsing for RenderDoc formats.
"""

import re
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class FormatInfo:
    """Detailed information about a RenderDoc texture format."""
    format_string: str
    channels: List[str]  # ['R', 'G', 'B', 'A']
    channel_count: int
    bits_per_channel: int
    total_bits: int
    is_normalized: bool  # UNORM/SNORM vs UINT/SINT/FLOAT
    is_signed: bool      # SNORM/SINT vs UNORM/UINT/FLOAT
    is_float: bool       # FLOAT vs integer types
    is_srgb: bool        # _SRGB suffix
    is_compressed: bool  # BC/DXTC/ETC/ASTC formats
    compression_type: Optional[str] = None  # "BC1", "BC7", etc.
    byte_order: str = "little"  # little/big endian


class TextureFormat:
    """Parser for RenderDoc texture format strings."""
    
    # Common format patterns
    FORMAT_PATTERNS = {
        # Uncompressed formats
        r'^R(\d+)(?:G(\d+))?(?:B(\d+))?(?:A(\d+))?_(UNORM|SNORM|UINT|SINT|FLOAT)(?:_SRGB)?$': 'uncompressed',
        # Compressed formats
        r'^(BC[1-7]|DXT[1-5]|ETC2_RGB|ETC2_RGBA|ASTC_\d+x\d+)_(UNORM|SRGB)$': 'compressed',
        # Depth/stencil formats
        r'^(D\d+)(?:_(FLOAT|UNORM))?$': 'depth',
        r'^(D\d+_S\d+)(?:_(UNORM|UINT))?$': 'depth_stencil',
    }
    
    CHANNEL_NAMES = ['R', 'G', 'B', 'A']
    
    @classmethod
    def parse(cls, format_str: str) -> FormatInfo:
        """
        Parse a RenderDoc format string into structured information.
        
        Args:
            format_str: Format string like "R8G8B8A8_UNORM_SRGB"
            
        Returns:
            FormatInfo object with parsed details
        """
        format_str = format_str.strip()
        
        # Check for compressed formats first
        if cls._is_compressed(format_str):
            return cls._parse_compressed(format_str)
        
        # Parse uncompressed formats
        match = re.match(r'^R(\d+)(?:G(\d+))?(?:B(\d+))?(?:A(\d+))?_(UNORM|SNORM|UINT|SINT|FLOAT)(?:_SRGB)?$', 
                        format_str)
        
        if not match:
            raise ValueError(f"Unsupported format: {format_str}")
        
        # Extract channel bit depths
        r_bits = int(match.group(1))
        g_bits = int(match.group(2)) if match.group(2) else 0
        b_bits = int(match.group(3)) if match.group(3) else 0
        a_bits = int(match.group(4)) if match.group(4) else 0
        
        # Get data type
        data_type = match.group(5)
        is_srgb = '_SRGB' in format_str
        
        # Build channel list
        channels = []
        channel_bits = []
        if r_bits > 0:
            channels.append('R')
            channel_bits.append(r_bits)
        if g_bits > 0:
            channels.append('G')
            channel_bits.append(g_bits)
        if b_bits > 0:
            channels.append('B')
            channel_bits.append(b_bits)
        if a_bits > 0:
            channels.append('A')
            channel_bits.append(a_bits)
        
        # Determine properties
        is_normalized = data_type in ('UNORM', 'SNORM')
        is_signed = data_type in ('SNORM', 'SINT')
        is_float = data_type == 'FLOAT'
        
        total_bits = sum(channel_bits)
        
        return FormatInfo(
            format_string=format_str,
            channels=channels,
            channel_count=len(channels),
            bits_per_channel=max(channel_bits) if channel_bits else 0,
            total_bits=total_bits,
            is_normalized=is_normalized,
            is_signed=is_signed,
            is_float=is_float,
            is_srgb=is_srgb,
            is_compressed=False
        )
    
    @classmethod
    def _is_compressed(cls, format_str: str) -> bool:
        """Check if format is a compressed format."""
        compressed_patterns = [
            r'^BC[1-7]',
            r'^DXT[1-5]',
            r'^ETC2_',
            r'^ASTC_'
        ]
        return any(re.match(pattern, format_str) for pattern in compressed_patterns)
    
    @classmethod
    def _parse_compressed(cls, format_str: str) -> FormatInfo:
        """Parse compressed format strings."""
        # Extract compression type
        compression_match = re.match(r'^(BC[1-7]|DXT[1-5]|ETC2_[A-Z]+|ASTC_\d+x\d+)', format_str)
        if not compression_match:
            raise ValueError(f"Unrecognized compressed format: {format_str}")
        
        compression_type = compression_match.group(1)
        is_srgb = '_SRGB' in format_str
        
        return FormatInfo(
            format_string=format_str,
            channels=['R', 'G', 'B', 'A'],  # Assume RGBA for compressed
            channel_count=4,
            bits_per_channel=8,  # Standard assumption
            total_bits=32,
            is_normalized=True,
            is_signed=False,
            is_float=False,
            is_srgb=is_srgb,
            is_compressed=True,
            compression_type=compression_type
        )
    
    @classmethod
    def get_pil_mode(cls, format_info: FormatInfo) -> str:
        """
        Get the corresponding PIL mode for a format.
        
        Args:
            format_info: Parsed format information
            
        Returns:
            PIL mode string (e.g., 'RGB', 'RGBA', 'L')
        """
        if format_info.is_compressed:
            return 'RGBA'  # Decompressed to RGBA
        
        channels = format_info.channels
        has_alpha = 'A' in channels
        
        if format_info.channel_count == 1:
            return 'L'  # Grayscale
        elif format_info.channel_count == 2:
            return 'LA'  # Grayscale with alpha
        elif format_info.channel_count == 3:
            return 'RGB'
        elif format_info.channel_count == 4:
            return 'RGBA' if has_alpha else 'RGBX'
        else:
            # Fallback for unusual formats
            return 'RGBA'
    
    @classmethod
    def needs_conversion(cls, format_info: FormatInfo) -> bool:
        """
        Check if format needs conversion to standard 8-bit format.
        
        Args:
            format_info: Format to check
            
        Returns:
            True if conversion is needed
        """
        # Compressed formats always need decompression
        if format_info.is_compressed:
            return True
            
        # Non-8-bit formats need conversion
        if format_info.bits_per_channel != 8:
            return True
            
        # Float formats need conversion
        if format_info.is_float:
            return True
            
        # Signed normalized formats may need conversion
        if format_info.is_signed and format_info.is_normalized:
            return True
            
        return False