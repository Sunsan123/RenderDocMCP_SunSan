"""
Image export functionality for RenderDoc textures.
"""

import os
from typing import Optional, Dict, Any
from pathlib import Path

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

from .format_detector import TextureFormat, FormatInfo
from .texture_converter import PixelConverter


class ImageExporter:
    """Exports RenderDoc textures to standard image formats."""
    
    SUPPORTED_FORMATS = ['PNG', 'JPEG', 'BMP', 'TIFF']
    
    def __init__(self):
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL (Pillow) is required for image export. Install with: pip install Pillow")
    
    def export_texture_to_image(
        self,
        data: bytes,
        format_info: FormatInfo,
        width: int,
        height: int,
        output_path: str,
        image_format: str = 'PNG',
        quality: int = 95,
        apply_gamma: bool = True
    ) -> Dict[str, Any]:
        """
        Export texture data to an image file.
        
        Args:
            data: Raw texture data
            format_info: Source format information
            width: Texture width
            height: Texture height
            output_path: Output file path
            image_format: Target image format ('PNG', 'JPEG', 'BMP', 'TIFF')
            quality: JPEG quality (1-100)
            apply_gamma: Whether to apply gamma correction for sRGB textures
            
        Returns:
            Dictionary with export results and metadata
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")
        
        # Validate parameters
        if image_format.upper() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported image format: {image_format}")
        
        if not (1 <= quality <= 100):
            raise ValueError("Quality must be between 1 and 100")
        
        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Convert to RGBA8 if needed
            if TextureFormat.needs_conversion(format_info) or format_info.is_compressed:
                rgba_data = PixelConverter.to_rgba8(data, format_info, width, height)
            else:
                rgba_data = data
            
            # Apply gamma correction if requested and needed
            if apply_gamma and format_info.is_srgb:
                rgba_data = PixelConverter.apply_gamma_correction(rgba_data, True)
            
            # Create PIL Image
            pil_mode = TextureFormat.get_pil_mode(format_info)
            if pil_mode == 'RGBA' and len(rgba_data) == width * height * 4:
                image = Image.frombuffer('RGBA', (width, height), rgba_data, 'raw', 'RGBA', 0, 1)
            elif pil_mode == 'RGB' and len(rgba_data) >= width * height * 3:
                # Extract RGB data
                rgb_data = bytearray()
                for i in range(width * height):
                    rgb_data.extend(rgba_data[i*4:i*4+3])
                image = Image.frombuffer('RGB', (width, height), bytes(rgb_data), 'raw', 'RGB', 0, 1)
            else:
                # Fallback - create from RGBA and convert
                image = Image.frombuffer('RGBA', (width, height), rgba_data, 'raw', 'RGBA', 0, 1)
                if pil_mode != 'RGBA':
                    image = image.convert(pil_mode)
            
            # Save image
            save_kwargs = {}
            if image_format.upper() == 'JPEG':
                # JPEG doesn't support alpha, convert to RGB
                if image.mode in ('RGBA', 'LA'):
                    # Composite with white background
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'RGBA':
                        background.paste(image, mask=image.split()[-1])
                    else:
                        background.paste(image)
                    image = background
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
            elif image_format.upper() == 'PNG':
                save_kwargs['optimize'] = True
            
            image.save(str(output_path), format=image_format.upper(), **save_kwargs)
            
            # Get file information
            stat = output_path.stat()
            
            return {
                'success': True,
                'output_path': str(output_path.absolute()),
                'format': image_format.upper(),
                'width': width,
                'height': height,
                'file_size': stat.st_size,
                'mode': image.mode,
                'converted_from': format_info.format_string if TextureFormat.needs_conversion(format_info) else None,
                'gamma_corrected': apply_gamma and format_info.is_srgb,
                'compression': format_info.compression_type if format_info.is_compressed else None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output_path': str(output_path.absolute()) if output_path.exists() else None
            }
    
    def export_to_png(
        self,
        data: bytes,
        format_info: FormatInfo,
        width: int,
        height: int,
        output_path: str,
        apply_gamma: bool = True
    ) -> Dict[str, Any]:
        """Convenience method for PNG export."""
        return self.export_texture_to_image(
            data, format_info, width, height, output_path, 
            image_format='PNG', apply_gamma=apply_gamma
        )
    
    def export_to_jpeg(
        self,
        data: bytes,
        format_info: FormatInfo,
        width: int,
        height: int,
        output_path: str,
        quality: int = 95,
        apply_gamma: bool = True
    ) -> Dict[str, Any]:
        """Convenience method for JPEG export."""
        return self.export_texture_to_image(
            data, format_info, width, height, output_path,
            image_format='JPEG', quality=quality, apply_gamma=apply_gamma
        )
    
    @staticmethod
    def get_supported_formats() -> list:
        """Get list of supported export formats."""
        return ImageExporter.SUPPORTED_FORMATS.copy()
    
    @staticmethod
    def is_format_supported(format_name: str) -> bool:
        """Check if an image format is supported."""
        return format_name.upper() in ImageExporter.SUPPORTED_FORMATS


class TextureConverter:
    """High-level texture conversion interface."""
    
    def __init__(self):
        self.exporter = ImageExporter()
    
    def convert_and_export(
        self,
        texture_data: bytes,
        texture_format: str,
        width: int,
        height: int,
        output_path: str,
        target_format: str = 'PNG',
        quality: int = 95,
        apply_gamma: bool = True
    ) -> Dict[str, Any]:
        """
        Convert RenderDoc texture and export to image file.
        
        Args:
            texture_data: Raw texture data from RenderDoc
            texture_format: RenderDoc format string (e.g., "R8G8B8A8_UNORM_SRGB")
            width: Texture width
            height: Texture height
            output_path: Output file path
            target_format: Target image format
            quality: JPEG quality
            apply_gamma: Apply gamma correction
            
        Returns:
            Export result dictionary
        """
        try:
            # Parse format
            format_info = TextureFormat.parse(texture_format)
            
            # Export
            result = self.exporter.export_texture_to_image(
                texture_data, format_info, width, height, output_path,
                image_format=target_format, quality=quality, apply_gamma=apply_gamma
            )
            
            # Add format information
            result['source_format'] = texture_format
            result['channels'] = format_info.channels
            result['bits_per_channel'] = format_info.bits_per_channel
            result['is_srgb'] = format_info.is_srgb
            result['is_compressed'] = format_info.is_compressed
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output_path': str(Path(output_path).absolute()) if Path(output_path).exists() else None
            }