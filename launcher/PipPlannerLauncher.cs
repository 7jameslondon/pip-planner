using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace PipPlannerLauncher
{
    internal static class Program
    {
        private static readonly Stopwatch StartupClock = Stopwatch.StartNew();

        [STAThread]
        private static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SplashForm(args));
        }

        internal static void RecordEvent(string name)
        {
            double elapsedMs = StartupClock.Elapsed.TotalMilliseconds;
            string timingFile = Environment.GetEnvironmentVariable("PIP_PLANNER_STARTUP_TIMING_FILE") ?? "";
            if (!string.IsNullOrWhiteSpace(timingFile))
            {
                string payload = string.Format(
                    "{{\"event\":\"{0}\",\"elapsed_ms\":{1:0.###},\"pid\":{2},\"mode\":\"native-portable-launcher\",\"packaged\":true}}{3}",
                    name,
                    elapsedMs,
                    Process.GetCurrentProcess().Id,
                    Environment.NewLine
                );
                try
                {
                    File.AppendAllText(timingFile, payload, new UTF8Encoding(false));
                }
                catch
                {
                    // Timing output must never block app launch.
                }
            }

            if (Environment.GetEnvironmentVariable("PIP_PLANNER_STARTUP_TIMING_STDOUT") == "1")
            {
                Console.WriteLine("launcher-timing-" + name + "-ms=" + elapsedMs.ToString("0.0"));
            }
        }
    }

    internal sealed class SplashForm : Form
    {
        private const string PayloadMagicText = "PIPPLANNERPKGv1";
        private const int PayloadHashLength = 64;

        private readonly string[] args;
        private readonly System.Windows.Forms.Timer closeTimer;
        private Label statusLabel;
        private Process childProcess;
        private DateTime childStartedAt;

        internal SplashForm(string[] args)
        {
            this.args = args;
            Width = 420;
            Height = 260;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.None;
            BackColor = Color.White;
            ShowInTaskbar = true;
            Text = "PIP Planner";

            Controls.Add(BuildContent());

            closeTimer = new System.Windows.Forms.Timer();
            closeTimer.Interval = 150;
            closeTimer.Tick += CloseTimerTick;
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            Program.RecordEvent("launcher-splash-shown");

            if (Environment.GetEnvironmentVariable("PIP_PLANNER_LAUNCHER_SMOKE") == "1")
            {
                closeTimer.Start();
                return;
            }

            BeginInvoke(new Action(StartPlanner));
        }

        private Control BuildContent()
        {
            Panel border = new Panel();
            border.Dock = DockStyle.Fill;
            border.BackColor = Color.White;
            border.Paint += (sender, e) =>
            {
                using (Pen pen = new Pen(Color.Black, 1))
                {
                    e.Graphics.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
                }
            };

            Label title = new Label();
            title.AutoSize = true;
            title.Text = "PIP Planner";
            title.Font = new Font("Georgia", 34, FontStyle.Bold, GraphicsUnit.Pixel);
            title.Location = new Point(34, 30);

            Panel rule = new Panel();
            rule.BackColor = Color.Black;
            rule.Location = new Point(34, 70);
            rule.Size = new Size(154, 3);

            Spinner spinner = new Spinner();
            spinner.Location = new Point(34, 104);
            spinner.Size = new Size(22, 22);

            statusLabel = new Label();
            statusLabel.AutoSize = true;
            statusLabel.Text = "Starting chemistry engine...";
            statusLabel.Font = new Font("Arial", 13, FontStyle.Regular, GraphicsUnit.Pixel);
            statusLabel.ForeColor = Color.FromArgb(51, 51, 51);
            statusLabel.Location = new Point(68, 106);

            MonomerSymbol im = new MonomerSymbol(true, "");
            im.Location = new Point(34, 164);
            MonomerLine line1 = new MonomerLine();
            line1.Location = new Point(66, 174);
            MonomerSymbol py = new MonomerSymbol(false, "");
            py.Location = new Point(112, 164);
            MonomerLine line2 = new MonomerLine();
            line2.Location = new Point(144, 174);
            MonomerSymbol hp = new MonomerSymbol(false, "H");
            hp.Location = new Point(190, 164);

            border.Controls.Add(title);
            border.Controls.Add(rule);
            border.Controls.Add(spinner);
            border.Controls.Add(statusLabel);
            border.Controls.Add(im);
            border.Controls.Add(line1);
            border.Controls.Add(py);
            border.Controls.Add(line2);
            border.Controls.Add(hp);
            return border;
        }

        private void StartPlanner()
        {
            ThreadPool.QueueUserWorkItem(delegate { StartPlannerWorker(); });
        }

        private void StartPlannerWorker()
        {
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string executable = FindPlannerExecutable(baseDir);
                if (string.IsNullOrWhiteSpace(executable))
                {
                    ShowLaunchError(
                        "Could not find an embedded PIP Planner payload or a PIP Planner executable next to this launcher."
                    );
                    return;
                }

                SetStatus("Opening UI...");

                ProcessStartInfo startInfo = new ProcessStartInfo();
                startInfo.FileName = executable;
                startInfo.WorkingDirectory = Path.GetDirectoryName(executable);
                startInfo.UseShellExecute = false;
                startInfo.Arguments = QuoteArgs(args);

                Process started = Process.Start(startInfo);
                Program.RecordEvent("launcher-child-started");
                BeginUi(delegate
                {
                    childProcess = started;
                    childStartedAt = DateTime.UtcNow;
                    closeTimer.Start();
                });
            }
            catch (Exception ex)
            {
                ShowLaunchError("Could not launch PIP Planner: " + ex.Message);
            }
        }

        private void CloseTimerTick(object sender, EventArgs e)
        {
            if (Environment.GetEnvironmentVariable("PIP_PLANNER_LAUNCHER_SMOKE") == "1")
            {
                closeTimer.Stop();
                Close();
                return;
            }

            if (childProcess == null)
            {
                return;
            }

            try
            {
                childProcess.Refresh();
                if (childProcess.HasExited || childProcess.MainWindowHandle != IntPtr.Zero)
                {
                    closeTimer.Stop();
                    Close();
                    return;
                }
            }
            catch
            {
                closeTimer.Stop();
                Close();
                return;
            }

            if ((DateTime.UtcNow - childStartedAt).TotalSeconds > 60)
            {
                closeTimer.Stop();
                Close();
            }
        }

        private string FindPlannerExecutable(string baseDir)
        {
            PayloadInfo payload = ReadPayloadInfo();
            if (payload != null)
            {
                return ExtractEmbeddedPayload(payload);
            }

            string unpacked = Path.Combine(baseDir, "win-unpacked", "PIP Planner.exe");
            if (File.Exists(unpacked))
            {
                return unpacked;
            }

            string portable = Path.Combine(baseDir, "PIP Planner-0.1.0-x64.exe");
            if (File.Exists(portable))
            {
                return portable;
            }

            return "";
        }

        private string ExtractEmbeddedPayload(PayloadInfo payload)
        {
            string cacheRoot = Environment.GetEnvironmentVariable("PIP_PLANNER_PORTABLE_CACHE_ROOT") ?? "";
            if (string.IsNullOrWhiteSpace(cacheRoot))
            {
                cacheRoot = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            }
            if (string.IsNullOrWhiteSpace(cacheRoot))
            {
                cacheRoot = Path.GetTempPath();
            }

            string cacheKey = payload.Hash.Substring(0, 16);
            string cacheDir = Path.Combine(cacheRoot, "PIP Planner", "portable-cache", cacheKey);
            string plannerExe = Path.Combine(cacheDir, "PIP Planner.exe");
            string markerFile = Path.Combine(cacheDir, ".payload-sha256");

            if (File.Exists(plannerExe) && File.Exists(markerFile))
            {
                string marker = File.ReadAllText(markerFile, Encoding.ASCII).Trim();
                if (string.Equals(marker, payload.Hash, StringComparison.OrdinalIgnoreCase))
                {
                    Program.RecordEvent("launcher-payload-cache-hit");
                    return plannerExe;
                }
            }

            Program.RecordEvent("launcher-payload-cache-miss");
            SetStatus("Unpacking portable app...");

            if (Directory.Exists(cacheDir))
            {
                Directory.Delete(cacheDir, true);
            }
            Directory.CreateDirectory(cacheDir);

            string tempZip = Path.Combine(
                Path.GetTempPath(),
                "pip-planner-payload-" + cacheKey + "-" + Process.GetCurrentProcess().Id + ".zip"
            );

            try
            {
                Program.RecordEvent("launcher-payload-copy-start");
                CopyPayloadToFile(payload, tempZip);
                Program.RecordEvent("launcher-payload-copy-end");

                Program.RecordEvent("launcher-payload-extract-start");
                ZipFile.ExtractToDirectory(tempZip, cacheDir);
                Program.RecordEvent("launcher-payload-extract-end");
            }
            finally
            {
                try
                {
                    if (File.Exists(tempZip))
                    {
                        File.Delete(tempZip);
                    }
                }
                catch
                {
                    // Temp cleanup must not prevent launch.
                }
            }

            if (!File.Exists(plannerExe))
            {
                throw new InvalidOperationException("The embedded payload did not contain PIP Planner.exe.");
            }

            File.WriteAllText(markerFile, payload.Hash, Encoding.ASCII);
            return plannerExe;
        }

        private static void CopyPayloadToFile(PayloadInfo payload, string destination)
        {
            byte[] buffer = new byte[1024 * 1024];
            long remaining = payload.Length;

            using (FileStream source = File.OpenRead(payload.ExecutablePath))
            using (FileStream target = File.Create(destination))
            {
                source.Seek(payload.Offset, SeekOrigin.Begin);
                while (remaining > 0)
                {
                    int toRead = (int)Math.Min(buffer.Length, remaining);
                    int read = source.Read(buffer, 0, toRead);
                    if (read <= 0)
                    {
                        throw new EndOfStreamException("Unexpected end of embedded payload.");
                    }
                    target.Write(buffer, 0, read);
                    remaining -= read;
                }
            }
        }

        private static PayloadInfo ReadPayloadInfo()
        {
            byte[] magic = Encoding.ASCII.GetBytes(PayloadMagicText);
            long footerLength = 8 + PayloadHashLength + magic.Length;
            string executablePath = Application.ExecutablePath;

            using (FileStream stream = File.OpenRead(executablePath))
            {
                if (stream.Length < footerLength)
                {
                    return null;
                }

                stream.Seek(-footerLength, SeekOrigin.End);
                byte[] lengthBytes = ReadExact(stream, 8);
                byte[] hashBytes = ReadExact(stream, PayloadHashLength);
                byte[] magicBytes = ReadExact(stream, magic.Length);

                if (!BytesEqual(magicBytes, magic))
                {
                    return null;
                }

                long payloadLength = BitConverter.ToInt64(lengthBytes, 0);
                long payloadOffset = stream.Length - footerLength - payloadLength;
                if (payloadLength <= 0 || payloadOffset < 0)
                {
                    return null;
                }

                string hash = Encoding.ASCII.GetString(hashBytes).Trim();
                if (hash.Length != PayloadHashLength)
                {
                    return null;
                }

                return new PayloadInfo(executablePath, payloadOffset, payloadLength, hash);
            }
        }

        private static byte[] ReadExact(Stream stream, int count)
        {
            byte[] buffer = new byte[count];
            int offset = 0;
            while (offset < count)
            {
                int read = stream.Read(buffer, offset, count - offset);
                if (read <= 0)
                {
                    throw new EndOfStreamException();
                }
                offset += read;
            }
            return buffer;
        }

        private static bool BytesEqual(byte[] left, byte[] right)
        {
            if (left.Length != right.Length)
            {
                return false;
            }
            for (int index = 0; index < left.Length; index++)
            {
                if (left[index] != right[index])
                {
                    return false;
                }
            }
            return true;
        }

        private void SetStatus(string text)
        {
            BeginUi(delegate
            {
                if (statusLabel != null)
                {
                    statusLabel.Text = text;
                }
            });
        }

        private void ShowLaunchError(string message)
        {
            BeginUi(delegate
            {
                closeTimer.Stop();
                MessageBox.Show(
                    this,
                    message,
                    "PIP Planner failed to start",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                Close();
            });
        }

        private void BeginUi(Action action)
        {
            if (IsDisposed)
            {
                return;
            }

            try
            {
                BeginInvoke(action);
            }
            catch (InvalidOperationException)
            {
            }
        }

        private static string QuoteArgs(string[] values)
        {
            StringBuilder builder = new StringBuilder();
            foreach (string value in values)
            {
                if (builder.Length > 0)
                {
                    builder.Append(' ');
                }
                builder.Append('"');
                builder.Append(value.Replace("\"", "\\\""));
                builder.Append('"');
            }
            return builder.ToString();
        }
    }

    internal sealed class PayloadInfo
    {
        internal readonly string ExecutablePath;
        internal readonly long Offset;
        internal readonly long Length;
        internal readonly string Hash;

        internal PayloadInfo(string executablePath, long offset, long length, string hash)
        {
            ExecutablePath = executablePath;
            Offset = offset;
            Length = length;
            Hash = hash;
        }
    }

    internal sealed class Spinner : Control
    {
        private readonly System.Windows.Forms.Timer timer;
        private int angle;

        internal Spinner()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
            timer = new System.Windows.Forms.Timer();
            timer.Interval = 80;
            timer.Tick += (sender, e) =>
            {
                angle = (angle + 35) % 360;
                Invalidate();
            };
            timer.Start();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using (Pen basePen = new Pen(Color.FromArgb(208, 208, 208), 2))
            using (Pen topPen = new Pen(Color.Black, 2))
            {
                Rectangle rect = new Rectangle(3, 3, Width - 6, Height - 6);
                e.Graphics.DrawEllipse(basePen, rect);
                e.Graphics.DrawArc(topPen, rect, angle, 95);
            }
        }
    }

    internal sealed class MonomerLine : Control
    {
        internal MonomerLine()
        {
            Size = new Size(38, 4);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            using (Brush brush = new SolidBrush(Color.Black))
            {
                e.Graphics.FillRectangle(brush, 0, 0, Width, Height);
            }
        }
    }

    internal sealed class MonomerSymbol : Control
    {
        private readonly bool filled;
        private readonly string text;

        internal MonomerSymbol(bool filled, string text)
        {
            this.filled = filled;
            this.text = text;
            Size = new Size(24, 24);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            Rectangle rect = new Rectangle(2, 2, Width - 5, Height - 5);
            using (Brush brush = new SolidBrush(filled ? Color.Black : Color.White))
            using (Pen pen = new Pen(Color.Black, 3))
            {
                e.Graphics.FillEllipse(brush, rect);
                e.Graphics.DrawEllipse(pen, rect);
            }

            if (!string.IsNullOrEmpty(text))
            {
                using (Font font = new Font("Georgia", 15, FontStyle.Bold, GraphicsUnit.Pixel))
                using (Brush brush = new SolidBrush(Color.Black))
                using (StringFormat format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                {
                    e.Graphics.DrawString(text, font, brush, ClientRectangle, format);
                }
            }
        }
    }
}
