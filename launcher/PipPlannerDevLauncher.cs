using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace PipPlannerDevLauncher
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string projectRoot = AppDomain.CurrentDomain.BaseDirectory;
            string electronExe = Path.Combine(projectRoot, "node_modules", "electron", "dist", "electron.exe");
            if (!File.Exists(electronExe))
            {
                MessageBox.Show(
                    "Electron was not found. Run `pnpm install`, then double-click this launcher again.",
                    "PIP Planner Dev Launcher",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            try
            {
                string outputDir = Path.Combine(projectRoot, "output");
                Directory.CreateDirectory(outputDir);
                string logPath = Path.Combine(outputDir, "dev-launcher.log");
                string timingPath = Path.Combine(outputDir, "dev-launcher-startup.jsonl");
                string pythonExe = FindPython(projectRoot);

                File.AppendAllText(
                    logPath,
                    DateTime.Now.ToString("s") + " Starting PIP Planner Dev from " + projectRoot + Environment.NewLine
                );

                ProcessStartInfo startInfo = new ProcessStartInfo();
                startInfo.FileName = electronExe;
                startInfo.Arguments = ".";
                startInfo.WorkingDirectory = projectRoot;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = true;
                startInfo.EnvironmentVariables["PIP_PLANNER_DEV_LAUNCHER"] = "1";
                startInfo.EnvironmentVariables["PIP_PLANNER_DEV_LOG"] = logPath;
                startInfo.EnvironmentVariables["PIP_PLANNER_STARTUP_TIMING_FILE"] = timingPath;
                if (!String.IsNullOrEmpty(pythonExe))
                {
                    startInfo.EnvironmentVariables["PIP_PLANNER_PYTHON"] = pythonExe;
                    File.AppendAllText(logPath, "Using Python: " + pythonExe + Environment.NewLine);
                }
                else
                {
                    File.AppendAllText(logPath, "No Python executable was found by the launcher." + Environment.NewLine);
                }
                Process.Start(startInfo);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Could not start PIP Planner: " + ex.Message,
                    "PIP Planner Dev Launcher",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        private static string FindPython(string projectRoot)
        {
            string[] candidates = new string[]
            {
                Path.Combine(projectRoot, ".venv", "Scripts", "python.exe"),
                Path.Combine(projectRoot, "venv", "Scripts", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "miniconda3", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "anaconda3", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python312", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python311", "python.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python310", "python.exe")
            };

            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }

            return "";
        }
    }
}
