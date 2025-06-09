from dataclasses import dataclass

from .process import ProcessRunner


@dataclass
class CMake:
    source_path: str
    build_path: str
    install_path: str
    build_type: str = "Release"

    def configure(self, options: list[str] | None = None):
        """Run CMake configuration."""
        runner = ProcessRunner()
        runner.run_streaming(
            [
                "cmake",
                "-B",
                self.build_path,
                "-S",
                self.source_path,
                f"-DCMAKE_BUILD_TYPE={self.build_type}",
                f"-DCMAKE_INSTALL_PREFIX={self.install_path}",
                *([option for option in options] if options else []),
            ]
        )

    def build(self):
        """Run CMake build."""
        runner = ProcessRunner()
        runner.run_streaming(
            [
                "cmake",
                "--build",
                self.build_path,
                "--config",
                self.build_type,
                "--parallel",
                "--target",
                "install",
            ]
        )

    def install(self):
        """Run CMake install."""
        runner = ProcessRunner()
        runner.run_streaming(
            [
                "cmake",
                "--install",
                self.build_path,
                "--config",
                self.build_type,
            ]
        )
