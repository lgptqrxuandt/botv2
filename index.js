const axios = require("axios");
const config = require("./config.example.js");

async function getUserId(username) {
  try {
    const response = await axios.get(
      `https://api.roblox.com/users/get-by-username?username=${username}`
    );
    return response.data.Id;
  } catch (error) {
    console.error("Failed to fetch user ID:", error.message);
    process.exit(1);
  }
}

async function getUserPresence(userId) {
  try {
    const response = await axios.post(
      "https://presence.roblox.com/v1/presence/users",
      { userIds: [userId] }
    );
    return response.data.userPresences[0];
  } catch (error) {
    console.error("Failed to fetch user presence:", error.message);
    process.exit(1);
  }
}

async function generateJoinTicket(botCookie, placeId, jobId) {
  try {
    const session = axios.create({
      headers: { Cookie: `.ROBLOSECURITY=${botCookie}` },
    });

    // Get CSRF token
    const csrfResponse = await session.post(
      "https://auth.roblox.com/v1/authentication-ticket"
    );
    const csrfToken = csrfResponse.headers["x-csrf-token"];

    // Request teleport ticket
    const teleportResponse = await session.post(
      "https://www.roblox.com/games/teleport",
      null,
      {
        params: { placeId, gameId: jobId },
        headers: { "X-CSRF-TOKEN": csrfToken },
        maxRedirects: 0,
        validateStatus: (status) => status === 302,
      }
    );

    // Extract ticket from redirect URL
    const joinUrl = teleportResponse.headers.location;
    const ticket = new URL(joinUrl).searchParams.get("ticket");
    return ticket;
  } catch (error) {
    console.error("Failed to generate join ticket:", error.message);
    process.exit(1);
  }
}

async function main() {
  console.log("Starting Roblox bot...");

  // Get target user's ID
  const targetUserId = await getUserId(config.TARGET_USERNAME);
  console.log(`Found user ID: ${targetUserId}`);

  // Check if user is in a game
  const presence = await getUserPresence(targetUserId);
  if (presence.userPresenceType !== 2) {
    console.error("Error: User is not in a game.");
    process.exit(1);
  }

  const placeId = presence.placeId;
  const jobId = presence.gameId;
  console.log(`Found game (Place ID: ${placeId}, Job ID: ${jobId})`);

  // Generate join ticket
  const ticket = await generateJoinTicket(
    config.BOT_COOKIE,
    placeId,
    jobId
  );
  console.log("Generated join ticket:", ticket);

  // Construct Roblox deep link
  const robloxLink = `roblox://placeId=${placeId}&gameId=${jobId}&ticket=${ticket}`;
  console.log(`\nPaste this in browser to join:\n${robloxLink}\n`);

  // Optional: Auto-launch (requires Roblox client)
  console.log("Waiting before joining...");
  await new Promise((resolve) => setTimeout(resolve, config.JOIN_DELAY));
  console.log("Attempting to launch Roblox...");
  const open = (await import("open")).default;
  await open(robloxLink);
}

main();
