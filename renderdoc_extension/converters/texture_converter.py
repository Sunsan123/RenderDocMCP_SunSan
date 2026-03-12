"""
Pixel data conversion utilities for RenderDoc textures.
"""

import struct
import numpy as np
from typing import Tuple, Optional
from .format_detector import FormatInfo, TextureFormat


class PixelConverter:
    """Converts RenderDoc texture data to standard formats."""
    
    @staticmethod
    def to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """
        Convert texture data to RGBA8 format.
        
        Args:
            data: Raw texture data bytes
            format_info: Source format information
            width: Texture width
            height: Texture height
            
        Returns:
            RGBA8 formatted bytes (width × height × 4)
        """
        if format_info.is_compressed:
            return PixelConverter._decompress_to_rgba8(data, format_info, width, height)
        
        # Handle uncompressed formats
        if not TextureFormat.needs_conversion(format_info):
            # Already in compatible format, may need channel reordering
            return PixelConverter._reorder_channels(data, format_info, width, height)
        
        # Convert based on data type
        if format_info.is_float:
            return PixelConverter._float_to_rgba8(data, format_info, width, height)
        elif format_info.is_signed and format_info.is_normalized:
            return PixelConverter._snorm_to_rgba8(data, format_info, width, height)
        elif format_info.is_normalized:
            return PixelConverter._unorm_to_rgba8(data, format_info, width, height)
        else:
            # Integer formats
            return PixelConverter._integer_to_rgba8(data, format_info, width, height)
    
    @staticmethod
    def _decompress_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """
        Decompress compressed formats to RGBA8.
        Note: This is a simplified implementation. For production use,
        consider using dedicated libraries like compressonator or DirectXTex.
        """
        if format_info.compression_type and format_info.compression_type.startswith('BC'):
            # Simplified BC decompression - in practice, use proper library
            block_width = 4
            block_height = 4
            bytes_per_block = 8 if format_info.compression_type in ['BC1', 'BC4'] else 16
            
            # For now, return a placeholder - real implementation would decode blocks
            num_blocks_x = (width + block_width - 1) // block_width
            num_blocks_y = (height + block_height - 1) // block_height
            expected_size = num_blocks_x * num_blocks_y * bytes_per_block
            
            if len(data) != expected_size:
                raise ValueError(f"Invalid BC data size: expected {expected_size}, got {len(data)}")
            
            # Placeholder: return solid color texture
            # In real implementation, decode each BC block
            rgba_data = bytearray(width * height * 4)
            for i in range(0, len(rgba_data), 4):
                rgba_data[i] = 128     # R
                rgba_data[i+1] = 128   # G
                rgba_data[i+2] = 128   # B
                rgba_data[i+3] = 255   # A
            return bytes(rgba_data)
        
        raise ValueError(f"Unsupported compressed format: {format_info.compression_type}")
    
    @staticmethod
    def _float_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """Convert floating-point formats to RGBA8."""
        total_pixels = width * height
        channels = format_info.channels
        channel_count = len(channels)
        
        # Parse float data
        if format_info.bits_per_channel == 32:
            fmt = '<' + 'f' * channel_count  # Little-endian floats
            struct_size = 4 * channel_count
        elif format_info.bits_per_channel == 16:
            # Half-float - convert manually
            return PixelConverter._half_float_to_rgba8(data, format_info, width, height)
        else:
            raise ValueError(f"Unsupported float bit depth: {format_info.bits_per_channel}")
        
        rgba_data = bytearray(total_pixels * 4)
        
        for i in range(total_pixels):
            offset = i * struct_size
            if offset + struct_size > len(data):
                break
                
            values = struct.unpack_from(fmt, data, offset)
            
            # Map float values [0.0, 1.0] to [0, 255]
            for j, channel in enumerate(['R', 'G', 'B', 'A']):
                if j < len(values):
                    float_val = max(0.0, min(1.0, values[j]))  # Clamp
                    byte_val = int(float_val * 255.0 + 0.5)
                else:
                    # Default values for missing channels
                    byte_val = 255 if channel == 'A' else 0
                    
                rgba_data[i * 4 + j] = byte_val
        
        return bytes(rgba_data)
    
    @staticmethod
    def _half_float_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """Convert 16-bit half-float to RGBA8."""
        # Simplified half-float conversion
        total_pixels = width * height
        channels = format_info.channels
        channel_count = len(channels)
        
        rgba_data = bytearray(total_pixels * 4)
        
        for i in range(total_pixels):
            offset = i * 2 * channel_count
            if offset + 2 * channel_count > len(data):
                break
                
            # Convert each half-float to float then to byte
            for j, channel in enumerate(['R', 'G', 'B', 'A']):
                if j < channel_count:
                    half_bytes = data[offset + j*2:offset + j*2 + 2]
                    float_val = PixelConverter._half_to_float(half_bytes)
                    float_val = max(0.0, min(1.0, float_val))  # Clamp
                    byte_val = int(float_val * 255.0 + 0.5)
                else:
                    byte_val = 255 if channel == 'A' else 0
                    
                rgba_data[i * 4 + j] = byte_val
        
        return bytes(rgba_data)
    
    @staticmethod
    def _half_to_float(half_bytes: bytes) -> float:
        """Convert 16-bit half-float to 32-bit float."""
        # Simplified implementation - in practice use numpy or struct
        if len(half_bytes) != 2:
            return 0.0
            
        # Decode IEEE 754 half-precision
        half = struct.unpack('<H', half_bytes)[0]
        sign = (half >> 15) & 0x1
        exp = (half >> 10) & 0x1F
        mant = half & 0x3FF
        
        if exp == 0:
            if mant == 0:
                return -0.0 if sign else 0.0
            else:
                # Subnormal number
                return (-1)**sign * 2**(-14) * (mant / 1024.0)
        elif exp == 31:
            if mant == 0:
                return float('-inf') if sign else float('inf')
            else:
                return float('nan')
        else:
            # Normal number
            return (-1)**sign * 2**(exp - 15) * (1.0 + mant / 1024.0)
    
    @staticmethod
    def _unorm_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """Convert unsigned normalized formats to RGBA8."""
        return PixelConverter._normalized_to_rgba8(data, format_info, width, height, signed=False)
    
    @staticmethod
    def _snorm_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """Convert signed normalized formats to RGBA8."""
        return PixelConverter._normalized_to_rgba8(data, format_info, width, height, signed=True)
    
    @staticmethod
    def _normalized_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int, 
                           signed: bool) -> bytes:
        """Convert normalized formats to RGBA8."""
        total_pixels = width * height
        channels = format_info.channels
        channel_count = len(channels)
        bits_per_channel = format_info.bits_per_channel
        
        # Calculate bytes per pixel
        bytes_per_pixel = (channel_count * bits_per_channel + 7) // 8
        bits_per_pixel = channel_count * bits_per_channel
        
        rgba_data = bytearray(total_pixels * 4)
        
        for i in range(total_pixels):
            offset = i * bytes_per_pixel
            if offset + bytes_per_pixel > len(data):
                break
            
            # Extract channel values
            channel_values = []
            bit_offset = 0
            
            for j in range(channel_count):
                # Extract bits for this channel
                if bits_per_channel <= 8:
                    byte_idx = bit_offset // 8
                    bit_shift = bit_offset % 8
                    mask = (1 << bits_per_channel) - 1
                    
                    if byte_idx < len(data) - offset:
                        byte_val = data[offset + byte_idx]
                        channel_val = (byte_val >> bit_shift) & mask
                    else:
                        channel_val = 0
                        
                elif bits_per_channel <= 16:
                    byte_idx = bit_offset // 8
                    if byte_idx + 1 < len(data) - offset:
                        channel_val = struct.unpack_from('<H', data, offset + byte_idx)[0]
                        channel_val &= (1 << bits_per_channel) - 1
                    else:
                        channel_val = 0
                else:
                    channel_val = 0
                
                # Normalize to [0, 255] or [-128, 127] for signed
                if signed:
                    max_val = (1 << (bits_per_channel - 1)) - 1
                    min_val = -(1 << (bits_per_channel - 1))
                    # Convert from [-max_val, max_val] to [-128, 127] then to [0, 255]
                    normalized = max(-1.0, min(1.0, channel_val / max_val))
                    byte_val = int((normalized * 0.5 + 0.5) * 255.0 + 0.5)
                else:
                    max_val = (1 << bits_per_channel) - 1
                    normalized = channel_val / max_val
                    byte_val = int(normalized * 255.0 + 0.5)
                
                channel_values.append(byte_val)
                bit_offset += bits_per_channel
            
            # Map to RGBA
            for j, channel in enumerate(['R', 'G', 'B', 'A']):
                if j < len(channel_values):
                    byte_val = channel_values[j]
                else:
                    # Default values
                    byte_val = 255 if channel == 'A' else 0
                
                rgba_data[i * 4 + j] = byte_val
        
        return bytes(rgba_data)
    
    @staticmethod
    def _integer_to_rgba8(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """Convert integer formats to RGBA8 (normalize by max value)."""
        total_pixels = width * height
        channels = format_info.channels
        channel_count = len(channels)
        bits_per_channel = format_info.bits_per_channel
        
        bytes_per_pixel = (channel_count * bits_per_channel + 7) // 8
        rgba_data = bytearray(total_pixels * 4)
        
        max_val = (1 << bits_per_channel) - 1
        
        for i in range(total_pixels):
            offset = i * bytes_per_pixel
            if offset + bytes_per_pixel > len(data):
                break
            
            # Extract and normalize each channel
            for j, channel in enumerate(['R', 'G', 'B', 'A']):
                if j < channel_count and j * (bits_per_channel // 8) < bytes_per_pixel:
                    if bits_per_channel <= 8:
                        byte_idx = j
                        if offset + byte_idx < len(data):
                            channel_val = data[offset + byte_idx]
                        else:
                            channel_val = 0
                    elif bits_per_channel <= 16:
                        byte_idx = j * 2
                        if offset + byte_idx + 1 < len(data):
                            channel_val = struct.unpack_from('<H', data, offset + byte_idx)[0]
                        else:
                            channel_val = 0
                    elif bits_per_channel <= 32:
                        byte_idx = j * 4
                        if offset + byte_idx + 3 < len(data):
                            channel_val = struct.unpack_from('<I', data, offset + byte_idx)[0]
                        else:
                            channel_val = 0
                    else:
                        channel_val = 0
                    
                    # Normalize to [0, 255]
                    normalized = min(1.0, channel_val / max_val)
                    byte_val = int(normalized * 255.0 + 0.5)
                else:
                    # Default values
                    byte_val = 255 if channel == 'A' else 0
                
                rgba_data[i * 4 + j] = byte_val
        
        return bytes(rgba_data)
    
    @staticmethod
    def _reorder_channels(data: bytes, format_info: FormatInfo, width: int, height: int) -> bytes:
        """Reorder channels if needed (e.g., BGRA to RGBA)."""
        if format_info.channels == ['B', 'G', 'R', 'A']:
            # BGRA to RGBA
            rgba_data = bytearray(len(data))
            for i in range(0, len(data), 4):
                if i + 3 < len(data):
                    rgba_data[i] = data[i + 2]    # R = B
                    rgba_data[i + 1] = data[i + 1]  # G = G
                    rgba_data[i + 2] = data[i]      # B = R
                    rgba_data[i + 3] = data[i + 3]  # A = A
            return bytes(rgba_data)
        else:
            # No reordering needed
            return data
    
    @staticmethod
    def apply_gamma_correction(data: bytes, is_srgb: bool) -> bytes:
        """
        Apply gamma correction for sRGB textures.
        
        Args:
            data: RGBA8 data
            is_srgb: Whether the data is in sRGB color space
            
        Returns:
            Gamma-corrected data
        """
        if not is_srgb:
            return data
        
        # Convert sRGB to linear RGB
        corrected = bytearray(len(data))
        
        for i in range(0, len(data), 4):
            # Process RGB channels (skip alpha)
            for j in range(3):  # R, G, B
                if i + j < len(data):
                    srgb_val = data[i + j] / 255.0
                    # sRGB to linear conversion
                    if srgb_val <= 0.04045:
                        linear = srgb_val / 12.92
                    else:
                        linear = ((srgb_val + 0.055) / 1.055) ** 2.4
                    corrected[i + j] = int(linear * 255.0 + 0.5)
            
            # Copy alpha unchanged
            if i + 3 < len(data):
                corrected[i + 3] = data[i + 3]
        
        return bytes(corrected)