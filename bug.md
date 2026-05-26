# Bug Report: UnicodeDecodeError in subprocess

## 错误现象

运行shell命令时出现以下错误：

```
Exception in thread Thread-23 (_readerthread):
Traceback (most recent call last):
  File "C:\Anaconda\lib\threading.py", line 1016, in _bootstrap_inner
    self.run()
  File "C:\Anaconda\lib\threading.py", line 953, in run
    self._target(*self._args, **self._kwargs)
  File "C:\Anaconda\lib\subprocess.py", line 1499, in _readerthread
    buffer.append(fh.read())
UnicodeDecodeError: 'gbk' codec can't decode byte 0xa0 in position 249: illegal multibyte sequence
  → found 1 match line(s)
```

## 原因分析

1. **编码问题**：Python的`subprocess`模块在读取外部命令输出时，使用系统默认编码（中文Windows上是GBK）
2. **输出内容**：外部命令的输出包含非GBK编码的字符（可能是UTF-8编码）
3. **解码失败**：当尝试用GBK解码UTF-8编码的字节时，遇到无法识别的字节序列（0xa0），抛出UnicodeDecodeError

## 相关代码位置

- **文件**：`src/xcode_cli/core/tools/shell.py`
- **行号**：10-17
- **代码**：
  ```python
  proc = subprocess.run(
      command,
      shell=True,
      cwd=cwd,
      capture_output=True,
      text=True,  # 使用系统默认编码解码输出
      timeout=timeout / 1000,
  )
  ```

## 解决方案

修改`shell.py`文件，添加编码参数：

```python
proc = subprocess.run(
    command,
    shell=True,
    cwd=cwd,
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    timeout=timeout / 1000,
)
```

### 参数说明：
- `encoding='utf-8'`：显式指定UTF-8编码，避免使用系统默认的GBK
- `errors='replace'`：遇到无法解码的字符时，用替换字符（�）代替，而不是抛出异常

## 影响范围

- 所有使用`run_shell`工具执行的命令
- 特别是输出包含中文或特殊字符的命令

## 测试建议

修复后测试以下命令：
1. `echo "你好世界"` - 测试中文输出
2. `dir` - 测试Windows命令输出
3. `python -c "print('测试')"` - 测试Python输出

## 备注

此问题主要出现在中文Windows系统上，因为系统默认编码是GBK，而很多工具输出使用UTF-8编码。