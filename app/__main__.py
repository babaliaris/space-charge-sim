"""Start the GUI:  python -m app   (from the repository root), or the packaged executable."""
import multiprocessing


def selftest():
    """Headless check of the packaged program (solver, quadrature, worker processes): exit code 0 if it works."""
    import sys

    from app import engine
    from app.inputs import defaults
    v = defaults()
    # a fixed end time (not the whole front), so that the check stays short and does not change with the defaults
    v.update(until_crest=False, t_end_us=6.0, max_bursts=0, n_time=20, n_snap=2, n_z=12, workers=2)
    result = engine.run(v, "selftest", message=print)
    expected = [9.47, 5.98]            # burst charges [nC] of the final model in this case (D = 40 cm, 100 us front)
    charges = [c["Q_nC"] for c in result.clouds]
    ok = len(charges) == len(expected) and all(abs(q - e) < 0.05 for q, e in zip(charges, expected))
    print("SELFTEST", "PASSED" if ok else "FAILED", [round(c["Q_nC"], 3) for c in result.clouds])
    sys.exit(0 if ok else 1)


def main():
    import os
    import sys

    if "--selftest" in sys.argv:
        selftest()

    from PyQt5.QtCore import QLocale
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QApplication

    from app import APP_NAME
    from app.window import MainWindow

    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))   # decimal point, not comma
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":      # the guard matters: the worker processes re-import this module
    multiprocessing.freeze_support()   # in the packaged executable the workers start through here
    main()
