package orsc.multiclient;

import orsc.CurrentInstalledLaunch;

import com.openrsc.client.model.Sprite;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;

import orsc.Config;

public interface ClientPort {

	boolean drawLoading(int i);

	void showLoadingProgress(int percentage, String status);

	void initListeners();

	void crashed();

	void drawLoadingError();

	void drawOutOfMemoryError();

	boolean isDisplayable();

	void drawTextBox(String line2, byte var2, String line1);

	void initGraphics();

	void draw();

	void close();

	String getCacheLocation();

	Sprite getBattery(int level);

	int getBatteryPercent();

	boolean getBatteryCharging();

	Sprite getConnectivity(int level);

	String getConnectivityText();

	void resized();

	Sprite getSpriteFromByteArray(ByteArrayInputStream byteArrayInputStream);

	/**
	 * Compatibility hook for platform-owned byte-buffer playback. Platforms that
	 * use another maintained audio path may intentionally do nothing, but must not
	 * throw merely because this format is unsupported.
	 */
	void playSound(byte[] soundData, int offset, int dataLength);

	/**
	 * Stops platform-owned playback. Cleanup must be idempotent, safe before any
	 * playback, and non-throwing when a platform has no active sound resources.
	 */
	void stopSoundPlayer();

	void drawKeyboard();

	void closeKeyboard();

	void setTitle(String title);

	void setIconImage(String serverName);

	static boolean saveHideIp(int preference) {
		java.io.OutputStream fileout;
		try {
			fileout = orsc.CurrentInstalledLaunch.current() == null
				? new FileOutputStream(new File(Config.F_CACHE_DIR, "hideIp.txt")) : orsc.CurrentInstalledLaunch.openSideStateOutput("hideIp.txt");

			OutputStreamWriter outputWriter = new OutputStreamWriter(fileout);
			outputWriter.write("" + preference);
			outputWriter.close();
			return true;
		} catch (Exception ignored) {
		}
		return false;
	}

	static int loadHideIp() {
		try {
			FileInputStream in = new FileInputStream(orsc.CurrentInstalledLaunch.current() == null
				? new File(Config.F_CACHE_DIR, "hideIp.txt") : orsc.CurrentInstalledLaunch.sideState("hideIp.txt").toFile());
			InputStreamReader inputStreamReader = new InputStreamReader(in);
			BufferedReader bufferedReader = new BufferedReader(inputStreamReader);
			StringBuilder sb = new StringBuilder();
			String line;
			while ((line = bufferedReader.readLine()) != null) {
				sb.append(line);
			}
			in.close();

			return Integer.parseInt(sb.toString());
		} catch (Exception ignored) {
		}
		return 0;
	}

	static boolean saveCredentials(String creds) {
		java.io.OutputStream fileout;
		try {
			fileout = orsc.CurrentInstalledLaunch.current() == null
				? new FileOutputStream(new File(Config.F_CACHE_DIR, "credentials.txt")) : orsc.CurrentInstalledLaunch.openSideStateOutput("credentials.txt");

			OutputStreamWriter outputWriter = new OutputStreamWriter(fileout);
			outputWriter.write(creds);
			outputWriter.close();
			return true;
		} catch (Exception ignored) {
		}
		return false;
	}

	static String loadCredentials() {
		try {
			FileInputStream in = new FileInputStream(orsc.CurrentInstalledLaunch.current() == null
				? new File(Config.F_CACHE_DIR, "credentials.txt") : orsc.CurrentInstalledLaunch.sideState("credentials.txt").toFile());
			InputStreamReader inputStreamReader = new InputStreamReader(in);
			BufferedReader bufferedReader = new BufferedReader(inputStreamReader);
			StringBuilder sb = new StringBuilder();
			String line;
			while ((line = bufferedReader.readLine()) != null) {
				sb.append(line);
			}
			in.close();

			return sb.toString();
		} catch (Exception ignored) {
		}
		return "";
	}

	static String loadIP() {
		if (CurrentInstalledLaunch.current() != null) return CurrentInstalledLaunch.current().host();
		try {
			FileInputStream in = new FileInputStream(Config.F_CACHE_DIR + File.separator + "ip.txt");
			InputStreamReader inputStreamReader = new InputStreamReader(in);
			BufferedReader bufferedReader = new BufferedReader(inputStreamReader);
			StringBuilder sb = new StringBuilder();
			String line;
			while ((line = bufferedReader.readLine()) != null) {
				sb.append(line);
			}
			in.close();

			return sb.toString();
		} catch (Exception ignored) {
		}
		return "";
	}

	static int loadPort() {
		if (CurrentInstalledLaunch.current() != null) return CurrentInstalledLaunch.current().port();
		try {
			FileInputStream in = new FileInputStream(Config.F_CACHE_DIR + File.separator + "port.txt");
			InputStreamReader inputStreamReader = new InputStreamReader(in);
			BufferedReader bufferedReader = new BufferedReader(inputStreamReader);
			StringBuilder sb = new StringBuilder();
			String line;
			while ((line = bufferedReader.readLine()) != null) {
				sb.append(line);
			}
			in.close();

			return Integer.parseInt(sb.toString());
		} catch (Exception ignored) {
		}
		return 0;
	}
}
