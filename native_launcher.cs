using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class ParserForm : Form
{
    private const int PreviewLimit = 20000;
    private readonly RichTextBox inputBox;
    private readonly Button pasteButton;
    private readonly Button openButton;
    private readonly Button parseButton;
    private readonly Button clearButton;
    private readonly Button copyButton;
    private readonly RichTextBox outputBox;
    private readonly Label statusLabel;
    private string sourceHtml;
    private bool loadingSource;

    public ParserForm()
    {
        Text = "社媒文章清理器";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(700, 560);
        Size = new Size(1000, 780);
        Font = new Font("Microsoft YaHei UI", 9F);

        var layout = new TableLayoutPanel();
        layout.Dock = DockStyle.Fill;
        layout.Padding = new Padding(12);
        layout.ColumnCount = 1;
        layout.RowCount = 6;
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 45F));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 55F));
        Controls.Add(layout);

        var title = new Label();
        title.Text = "把文章 HTML 粘贴到这里";
        title.Font = new Font("Microsoft YaHei UI", 11F, FontStyle.Bold);
        title.AutoSize = true;
        title.Margin = new Padding(0, 0, 0, 6);
        layout.Controls.Add(title, 0, 0);

        inputBox = new RichTextBox();
        inputBox.Dock = DockStyle.Fill;
        inputBox.Font = new Font("Consolas", 10F);
        inputBox.WordWrap = true;
        inputBox.TextChanged += InputTextChanged;
        layout.Controls.Add(inputBox, 0, 1);

        var actions = new FlowLayoutPanel();
        actions.Dock = DockStyle.Fill;
        actions.AutoSize = true;
        actions.WrapContents = false;
        actions.Margin = new Padding(0, 8, 0, 0);
        layout.Controls.Add(actions, 0, 2);

        pasteButton = MakeButton("从剪贴板粘贴", PasteClicked);
        openButton = MakeButton("打开 HTML 文件", OpenClicked);
        parseButton = MakeButton("解析文章", ParseClicked);
        clearButton = MakeButton("清空", ClearClicked);
        copyButton = MakeButton("复制全部结果", CopyClicked);
        copyButton.Enabled = false;
        actions.Controls.Add(pasteButton);
        actions.Controls.Add(openButton);
        actions.Controls.Add(parseButton);
        actions.Controls.Add(clearButton);
        actions.Controls.Add(copyButton);

        statusLabel = new Label();
        statusLabel.Text = "粘贴或打开 HTML 后点击解析。结果会显示在下方。";
        statusLabel.AutoSize = true;
        statusLabel.ForeColor = Color.DimGray;
        statusLabel.Margin = new Padding(0, 10, 0, 0);
        layout.Controls.Add(statusLabel, 0, 3);

        var outputTitle = new Label();
        outputTitle.Text = "提取结果（Windows 原生文本框，可滚动、选中和 Ctrl+C 复制）";
        outputTitle.AutoSize = true;
        outputTitle.Font = new Font("Microsoft YaHei UI", 10F, FontStyle.Bold);
        outputTitle.Margin = new Padding(0, 10, 0, 6);
        layout.Controls.Add(outputTitle, 0, 4);

        outputBox = new RichTextBox();
        outputBox.Dock = DockStyle.Fill;
        outputBox.Font = new Font("Microsoft YaHei UI", 10F);
        outputBox.ReadOnly = true;
        outputBox.WordWrap = true;
        outputBox.ScrollBars = RichTextBoxScrollBars.Vertical;
        layout.Controls.Add(outputBox, 0, 5);
    }

    private Button MakeButton(string text, EventHandler handler)
    {
        var button = new Button();
        button.Text = text;
        button.AutoSize = true;
        button.Padding = new Padding(8, 3, 8, 3);
        button.Margin = new Padding(0, 0, 8, 0);
        button.Click += handler;
        return button;
    }

    private void InputTextChanged(object sender, EventArgs e)
    {
        if (!loadingSource)
        {
            sourceHtml = null;
        }
    }

    private void PasteClicked(object sender, EventArgs e)
    {
        if (!Clipboard.ContainsText())
        {
            MessageBox.Show("请先复制 HTML。", "剪贴板为空", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        LoadSource(Clipboard.GetText(), "已从剪贴板读取 HTML");
    }

    private void OpenClicked(object sender, EventArgs e)
    {
        using (var dialog = new OpenFileDialog())
        {
            dialog.Title = "选择 HTML 文件";
            dialog.Filter = "HTML 文件|*.html;*.htm|所有文件|*.*";
            if (dialog.ShowDialog(this) != DialogResult.OK)
            {
                return;
            }
            try
            {
                LoadSource(ReadHtml(dialog.FileName), "已打开：" + Path.GetFileName(dialog.FileName));
            }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, "打开失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }

    private static string ReadHtml(string path)
    {
        var bytes = File.ReadAllBytes(path);
        foreach (var encoding in new[] { new UTF8Encoding(true), new UTF8Encoding(false), Encoding.GetEncoding("GB18030") })
        {
            try
            {
                return encoding.GetString(bytes);
            }
            catch (DecoderFallbackException)
            {
            }
        }
        return Encoding.UTF8.GetString(bytes);
    }

    private void LoadSource(string value, string status)
    {
        sourceHtml = value;
        loadingSource = true;
        inputBox.Text = value.Length > PreviewLimit
            ? value.Substring(0, PreviewLimit) + "\r\n\r\n[输入区只显示前 20,000 个字符；解析仍使用完整 HTML。]"
            : value;
        loadingSource = false;
        statusLabel.Text = status + "（" + value.Length.ToString("N0") + " 个字符）";
    }

    private async void ParseClicked(object sender, EventArgs e)
    {
        var html = sourceHtml ?? inputBox.Text;
        if (String.IsNullOrWhiteSpace(html))
        {
            MessageBox.Show("请先粘贴文章 HTML，或打开 HTML 文件。", "还没有内容", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        SetBusy(true, "正在解析…");
        try
        {
            var result = await Task.Run(() => RunWorker(html));
            outputBox.Text = result;
            outputBox.Select(0, 0);
            outputBox.ScrollToCaret();
            copyButton.Enabled = result.Length > 0;
            sourceHtml = null;
            statusLabel.Text = "已完成。结果可直接滚动、选中或复制。";
        }
        catch (Exception error)
        {
            statusLabel.Text = "解析失败，可修改内容后重试。";
            MessageBox.Show(error.Message, "解析失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            SetBusy(false, null);
        }
    }

    private void ClearClicked(object sender, EventArgs e)
    {
        sourceHtml = null;
        loadingSource = true;
        inputBox.Clear();
        loadingSource = false;
        outputBox.Clear();
        copyButton.Enabled = false;
        statusLabel.Text = "已清空";
    }

    private void CopyClicked(object sender, EventArgs e)
    {
        if (outputBox.TextLength == 0)
        {
            return;
        }
        Clipboard.SetText(outputBox.Text);
        statusLabel.Text = "已复制全部结果";
    }

    private void SetBusy(bool busy, string status)
    {
        pasteButton.Enabled = !busy;
        openButton.Enabled = !busy;
        parseButton.Enabled = !busy;
        clearButton.Enabled = !busy;
        copyButton.Enabled = !busy && outputBox.TextLength > 0;
        UseWaitCursor = busy;
        if (status != null)
        {
            statusLabel.Text = status;
        }
    }

    private static string RunWorker(string html)
    {
        var directory = Path.Combine(Path.GetTempPath(), "social_article_parser");
        Directory.CreateDirectory(directory);
        var token = DateTime.UtcNow.Ticks.ToString();
        var inputPath = Path.Combine(directory, "input-" + token + ".html");
        var outputPath = Path.Combine(directory, "article-" + token + ".txt");
        try
        {
            File.WriteAllText(inputPath, html, new UTF8Encoding(false));
            var workerPath = ExtractWorker(directory);
            var startInfo = new ProcessStartInfo(workerPath, Quote(inputPath) + " " + Quote(outputPath));
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            using (var process = Process.Start(startInfo))
            {
                process.WaitForExit();
                if (process.ExitCode != 0 || !File.Exists(outputPath))
                {
                    throw new InvalidOperationException("解析组件未能完成。请关闭旧版本后重试。");
                }
            }
            return File.ReadAllText(outputPath, Encoding.UTF8);
        }
        finally
        {
            TryDelete(inputPath);
            TryDelete(outputPath);
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (IOException)
        {
        }
    }

    private static string ExtractWorker(string directory)
    {
        var workerPath = Path.Combine(directory, "social_article_parser_worker.exe");
        var assembly = Assembly.GetExecutingAssembly();
        using (var resource = assembly.GetManifestResourceStream("ParserWorker"))
        {
            if (resource == null)
            {
                throw new InvalidOperationException("解析组件缺失。");
            }
            if (File.Exists(workerPath) && new FileInfo(workerPath).Length == resource.Length)
            {
                return workerPath;
            }
            using (var target = File.Create(workerPath))
            {
                resource.CopyTo(target);
            }
        }
        return workerPath;
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new ParserForm());
    }
}
