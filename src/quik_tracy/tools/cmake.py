from dataclasses import dataclass

from .process import ProcessRunner


@dataclass
class CMake:
    source_path: str
    build_path: str
    install_path: str
    build_type: str = "Release"
    cpm_cache_path: str | None = None

    def configure(self, options: list[str] | None = None):
        """Run CMake configuration."""
        runner = ProcessRunner()

        cmd = [
            "cmake",
            "-B",
            self.build_path,
            "-S",
            self.source_path,
            f"-DCMAKE_BUILD_TYPE={self.build_type}",
            f"-DCMAKE_INSTALL_PREFIX={self.install_path}",
        ]

        # Add CPM cache path if specified (speeds up builds by sharing downloaded packages)
        if self.cpm_cache_path:
            cmd.append(f"-DCPM_SOURCE_CACHE={self.cpm_cache_path}")

        if options:
            cmd.extend(options)

        runner.run_streaming(cmd)

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
