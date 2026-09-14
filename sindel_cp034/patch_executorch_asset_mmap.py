#!/usr/bin/env python3
"""Deterministic CP034 patch for ExecuTorch Android v1.1.0.

Adds Java Module.loadAsset(AssetManager, assetPath, numThreads) and a native
fd64 -> mmap -> BufferDataLoader path. Refuses any upstream source drift.
The Build Factory also ensures the exact PyYAML codegen dependency needed by
ExecuTorch's generated operator bindings before native compilation begins.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

PINNED_COMMIT = "17adba19d0051b4a184f7ff7e7a0612cf8bd3000"
FILES = {
    "extension/android/executorch_android/src/main/java/org/pytorch/executorch/Module.java": "6da76bf4b74e2673597aa13c2bd0ef85f0e9a394",
    "extension/android/jni/jni_layer.cpp": "1f8457e00c591491481d80638cd7f79ba91ae640",
    "extension/android/CMakeLists.txt": "38b28a1407a6317781034decd0a4a4141c888db8",
}


def ensure_codegen_dependency() -> None:
    try:
        import yaml  # type: ignore
        if getattr(yaml, "__version__", None) == "6.0.2":
            return
    except Exception:
        pass
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyYAML==6.0.2"])
    import yaml  # type: ignore
    if getattr(yaml, "__version__", None) != "6.0.2":
        raise SystemExit("FAIL-CLOSED: PyYAML 6.0.2 codegen dependency not active")


def run(root: pathlib.Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=root, text=True).strip()


def git_blob_sha(path: pathlib.Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"FAIL-CLOSED: {label}: expected exact one anchor, got {count}")
    return text.replace(old, new, 1)


def patch_module_java(path: pathlib.Path) -> None:
    s = path.read_text(encoding="utf-8")
    s = replace_once(s, "import android.util.Log;\n", "import android.content.res.AssetManager;\nimport android.util.Log;\n", "Module.java import")
    s = replace_once(
        s,
        "  private static native HybridData initHybrid(\n      String moduleAbsolutePath, int loadMode, int initHybrid);\n",
        "  private static native HybridData initHybrid(\n      String moduleAbsolutePath, int loadMode, int initHybrid);\n\n"
        "  @DoNotStrip\n"
        "  private static native HybridData initHybridAsset(\n"
        "      AssetManager assetManager, String assetPath, int numThreads);\n",
        "Module.java native asset init",
    )
    anchor = "  public static Module load(final String modelPath, int loadMode) {\n    return load(modelPath, loadMode, 0);\n  }\n"
    insertion = anchor + "\n" + r'''  /**
   * Loads an ExecuTorch module directly from an uncompressed Android asset.
   * CP034 uses this for install-time asset-pack PTEs without copying them to filesDir.
   */
  public static Module loadAsset(
      final AssetManager assetManager, final String assetPath, final int numThreads) {
    if (assetManager == null) {
      throw new IllegalArgumentException("assetManager is null");
    }
    if (assetPath == null || assetPath.isEmpty()) {
      throw new IllegalArgumentException("assetPath is empty");
    }
    ExecuTorchRuntime runtime = ExecuTorchRuntime.getRuntime();
    return new Module(initHybridAsset(assetManager, assetPath, numThreads));
  }

  private Module(HybridData hybridData) {
    mHybridData = hybridData;
    mMethodMetadata = populateMethodMeta();
  }
'''
    s = replace_once(s, anchor, insertion, "Module.java public loadAsset")
    path.write_text(s, encoding="utf-8")


def patch_jni(path: pathlib.Path) -> None:
    s = path.read_text(encoding="utf-8")
    s = replace_once(
        s,
        "#include <executorch/extension/android/jni/log.h>\n#include <executorch/extension/module/module.h>\n",
        "#include <executorch/extension/android/jni/log.h>\n#include <executorch/extension/data_loader/buffer_data_loader.h>\n#include <executorch/extension/module/module.h>\n",
        "jni include BufferDataLoader",
    )
    s = replace_once(
        s,
        "#include <cassert>\n#include <chrono>\n",
        "#include <android/asset_manager.h>\n#include <android/asset_manager_jni.h>\n#include <sys/mman.h>\n#include <unistd.h>\n#include <cerrno>\n#include <cassert>\n#include <chrono>\n",
        "jni Android mmap includes",
    )
    s = replace_once(
        s,
        "namespace executorch::extension {\nclass TensorHybrid",
        r'''namespace executorch::extension {
class JAndroidAssetManager : public facebook::jni::JavaClass<JAndroidAssetManager> {
 public:
  static constexpr auto kJavaDescriptor = "Landroid/content/res/AssetManager;";
};

class MappedAndroidAsset final {
 public:
  MappedAndroidAsset(
      facebook::jni::alias_ref<JAndroidAssetManager> asset_manager,
      const std::string& asset_path) {
    JNIEnv* env = facebook::jni::Environment::current();
    AAssetManager* manager = AAssetManager_fromJava(env, asset_manager.get());
    if (manager == nullptr) {
      jni_helper::throwExecutorchException(
          static_cast<uint32_t>(Error::InvalidArgument),
          "AAssetManager_fromJava failed");
      return;
    }
    AAsset* asset = AAssetManager_open(manager, asset_path.c_str(), AASSET_MODE_RANDOM);
    if (asset == nullptr) {
      jni_helper::throwExecutorchException(
          static_cast<uint32_t>(Error::InvalidArgument),
          "Cannot open Android asset: " + asset_path);
      return;
    }
    off64_t start = 0;
    off64_t length = 0;
    int fd = AAsset_openFileDescriptor64(asset, &start, &length);
    AAsset_close(asset);
    if (fd < 0 || start < 0 || length <= 0) {
      if (fd >= 0) {
        close(fd);
      }
      jni_helper::throwExecutorchException(
          static_cast<uint32_t>(Error::InvalidArgument),
          "Asset is missing, empty, or compressed (fd64 unavailable): " + asset_path);
      return;
    }

    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0) {
      close(fd);
      jni_helper::throwExecutorchException(
          static_cast<uint32_t>(Error::InvalidState), "Invalid page size");
      return;
    }
    const off64_t aligned_start = start & ~static_cast<off64_t>(page_size - 1);
    const size_t delta = static_cast<size_t>(start - aligned_start);
    if (static_cast<uint64_t>(length) >
        static_cast<uint64_t>(std::numeric_limits<size_t>::max() - delta)) {
      close(fd);
      jni_helper::throwExecutorchException(
          static_cast<uint32_t>(Error::InvalidArgument), "Asset mmap length overflow");
      return;
    }
    mapping_size_ = delta + static_cast<size_t>(length);
    mapping_ = mmap(nullptr, mapping_size_, PROT_READ, MAP_PRIVATE, fd, aligned_start);
    const int saved_errno = errno;
    close(fd);
    if (mapping_ == MAP_FAILED) {
      mapping_ = nullptr;
      mapping_size_ = 0;
      jni_helper::throwExecutorchException(
          static_cast<uint32_t>(Error::InvalidState),
          "mmap Android asset failed errno=" + std::to_string(saved_errno));
      return;
    }
    data_ = static_cast<const uint8_t*>(mapping_) + delta;
    data_size_ = static_cast<size_t>(length);
  }

  ~MappedAndroidAsset() {
    if (mapping_ != nullptr) {
      munmap(mapping_, mapping_size_);
    }
  }
  MappedAndroidAsset(const MappedAndroidAsset&) = delete;
  MappedAndroidAsset& operator=(const MappedAndroidAsset&) = delete;
  const void* data() const { return data_; }
  size_t size() const { return data_size_; }

 private:
  void* mapping_ = nullptr;
  size_t mapping_size_ = 0;
  const uint8_t* data_ = nullptr;
  size_t data_size_ = 0;
};

class TensorHybrid''',
        "jni mapped asset class",
    )
    s = replace_once(s, "#include <memory>\n#include <sstream>\n", "#include <memory>\n#include <limits>\n#include <sstream>\n", "jni limits include")
    s = replace_once(
        s,
        "class ExecuTorchJni : public facebook::jni::HybridClass<ExecuTorchJni> {\n private:\n  friend HybridBase;\n  std::unique_ptr<Module> module_;\n",
        "class ExecuTorchJni : public facebook::jni::HybridClass<ExecuTorchJni> {\n private:\n"
        "  friend HybridBase;\n"
        "  // Declared before module_ so reverse destruction destroys Module before mmap.\n"
        "  std::unique_ptr<MappedAndroidAsset> mapped_asset_;\n"
        "  std::unique_ptr<Module> module_;\n",
        "jni lifetime fields",
    )
    s = replace_once(
        s,
        "  static facebook::jni::local_ref<jhybriddata> initHybrid(\n      facebook::jni::alias_ref<jclass>,\n      facebook::jni::alias_ref<jstring> modelPath,\n      jint loadMode,\n      jint numThreads) {\n    return makeCxxInstance(modelPath, loadMode, numThreads);\n  }\n",
        "  static facebook::jni::local_ref<jhybriddata> initHybrid(\n"
        "      facebook::jni::alias_ref<jclass>,\n"
        "      facebook::jni::alias_ref<jstring> modelPath,\n"
        "      jint loadMode,\n"
        "      jint numThreads) {\n"
        "    return makeCxxInstance(modelPath, loadMode, numThreads);\n"
        "  }\n\n"
        "  static facebook::jni::local_ref<jhybriddata> initHybridAsset(\n"
        "      facebook::jni::alias_ref<jclass>,\n"
        "      facebook::jni::alias_ref<JAndroidAssetManager> assetManager,\n"
        "      facebook::jni::alias_ref<jstring> assetPath,\n"
        "      jint numThreads) {\n"
        "    return makeCxxInstance(assetManager, assetPath, numThreads);\n"
        "  }\n",
        "jni initHybridAsset",
    )
    constructor_anchor = r'''  ExecuTorchJni(
      facebook::jni::alias_ref<jstring> modelPath,
      jint loadMode,
      jint numThreads) {
'''
    if s.count(constructor_anchor) != 1:
        raise SystemExit("FAIL-CLOSED: path constructor anchor drift")
    asset_ctor = r'''  ExecuTorchJni(
      facebook::jni::alias_ref<JAndroidAssetManager> assetManager,
      facebook::jni::alias_ref<jstring> assetPath,
      jint numThreads) {
    mapped_asset_ = std::make_unique<MappedAndroidAsset>(
        assetManager, assetPath->toStdString());
    auto data_loader = std::make_unique<BufferDataLoader>(
        mapped_asset_->data(), mapped_asset_->size());
#ifdef EXECUTORCH_ANDROID_PROFILING
    auto etdump_gen = std::make_unique<executorch::etdump::ETDumpGen>();
#else
    auto etdump_gen = nullptr;
#endif
    module_ = std::make_unique<Module>(
        std::move(data_loader), nullptr, nullptr, std::move(etdump_gen));

#ifdef ET_USE_THREADPOOL
    auto threadpool = executorch::extension::threadpool::get_threadpool();
    if (threadpool) {
      int thread_count =
          numThreads != 0 ? numThreads : cpuinfo_get_processors_count() / 2;
      if (thread_count > 0) {
        threadpool->_unsafe_reset_threadpool(thread_count);
      }
    }
#endif
  }

'''
    s = s.replace(constructor_anchor, asset_ctor + constructor_anchor, 1)
    s = replace_once(
        s,
        "        makeNativeMethod(\"initHybrid\", ExecuTorchJni::initHybrid),\n",
        "        makeNativeMethod(\"initHybrid\", ExecuTorchJni::initHybrid),\n"
        "        makeNativeMethod(\"initHybridAsset\", ExecuTorchJni::initHybridAsset),\n",
        "jni register initHybridAsset",
    )
    path.write_text(s, encoding="utf-8")


def patch_cmake(path: pathlib.Path) -> None:
    s = path.read_text(encoding="utf-8")
    s = replace_once(s, "target_link_libraries(executorch_jni ${link_libraries} log)", "target_link_libraries(executorch_jni ${link_libraries} log android)", "CMake android link")
    path.write_text(s, encoding="utf-8")


def main() -> int:
    ensure_codegen_dependency()
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=pathlib.Path)
    ap.add_argument("--skip-git-head", action="store_true", help="fixture self-test only")
    ns = ap.parse_args()
    root = ns.root.resolve()
    if not ns.skip_git_head:
        head = run(root, "git", "rev-parse", "HEAD")
        if head != PINNED_COMMIT:
            raise SystemExit(f"FAIL-CLOSED: ExecuTorch HEAD {head} != {PINNED_COMMIT}")

    for rel, expected in FILES.items():
        p = root / rel
        if not p.is_file():
            raise SystemExit(f"FAIL-CLOSED: missing upstream file {rel}")
        got = git_blob_sha(p)
        if got != expected:
            raise SystemExit(f"FAIL-CLOSED: upstream blob drift {rel}: {got} != {expected}")

    patch_module_java(root / next(iter(FILES)))
    patch_jni(root / "extension/android/jni/jni_layer.cpp")
    patch_cmake(root / "extension/android/CMakeLists.txt")

    module = (root / next(iter(FILES))).read_text(encoding="utf-8")
    jni = (root / "extension/android/jni/jni_layer.cpp").read_text(encoding="utf-8")
    cmake = (root / "extension/android/CMakeLists.txt").read_text(encoding="utf-8")
    required = [
        ("Module.loadAsset", "public static Module loadAsset" in module),
        ("native initHybridAsset", "initHybridAsset" in module and "initHybridAsset" in jni),
        ("fd64", "AAsset_openFileDescriptor64" in jni),
        ("mmap", "mmap(nullptr" in jni),
        ("BufferDataLoader", "BufferDataLoader" in jni),
        ("Module DataLoader ctor", "std::move(data_loader)" in jni),
        ("android link", "log android" in cmake),
    ]
    bad = [name for name, ok in required if not ok]
    if bad:
        raise SystemExit("FAIL-CLOSED: patch postcondition failed: " + ", ".join(bad))
    print("CP034_EXECUTORCH_ASSET_MMAP_PATCH_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
