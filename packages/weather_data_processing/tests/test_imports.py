"""
Simple test to verify package installation and imports.
"""

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    # Main module
    import grid_data_processing
    print(f"✓ grid_data_processing v{grid_data_processing.__version__}")
    
    # Main classes
    from grid_data_processing import GridDataProcessor
    print("✓ GridDataProcessor")
    
    # Gap filling
    from grid_data_processing.gap_filling import fill_all_gaps
    print("✓ fill_all_gaps")
    
    # Pipeline steps
    from grid_data_processing.pipeline.step1_combine_monthly import combine_monthly_files
    print("✓ combine_monthly_files")
    
    from grid_data_processing.pipeline.step3_temporal_aggregation import aggregate_to_half_hourly
    print("✓ aggregate_to_half_hourly")
    
    from grid_data_processing.pipeline.step4_timezone import set_timezone
    print("✓ set_timezone")
    
    # IO
    from grid_data_processing.io.config_loader import load_config
    print("✓ load_config")
    
    # Utils
    from grid_data_processing.utils.logging import setup_logging
    from grid_data_processing.utils.validation import validate_processed_data
    print("✓ utils")
    
    print("\n✅ All imports successful!")


def test_config():
    """Test configuration loading."""
    print("\nTesting configuration...")
    
    from grid_data_processing.io.config_loader import get_default_config
    
    config = get_default_config()
    
    assert "gap_filling" in config
    assert "aggregation" in config
    assert "timezone" in config
    
    print("✓ Default configuration loaded")
    print(f"  - Short gap threshold: {config['gap_filling']['short_gap_threshold_minutes']} min")
    print(f"  - Max search days: {config['gap_filling']['gradient']['max_search_days']}")
    print(f"  - Smooth window: {config['gap_filling']['gradient']['smooth_window_slots']}")
    print(f"  - Target timezone: {config['timezone']['target']}")
    
    print("\n✅ Configuration test passed!")


if __name__ == "__main__":
    test_imports()
    test_config()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)
    print("\nYou can now use the package!")
    print("\nTry:")
    print("  python -m grid_data_processing --help")
