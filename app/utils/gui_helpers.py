def disconnect_signal_safely(signal):
    """Safely disconnect a signal without raising exceptions."""
    try:
        signal.disconnect()
    except TypeError:
        pass