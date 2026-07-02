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
                ProcessStartInfo startInfo = new ProcessStartInfo();
                startInfo.FileName = electronExe;
                startInfo.Arguments = ".";
                startInfo.WorkingDirectory = projectRoot;
                startInfo.UseShellExecute = false;
                startInfo.CreateNoWindow = true;
                startInfo.EnvironmentVariables["PIP_PLANNER_DEV_LAUNCHER"] = "1";
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
    }
}
