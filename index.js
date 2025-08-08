import axios from "axios";
import fs from "fs";

const config = JSON.parse(fs.readFileSync("config.json"));
const cookie = config.robloxCookie;
const mainUsername = config.mainUsername;
const discordWebhook = config.discordWebhook;

let mainUserId = null;

// Send message to Discord webhook
async function sendToDiscord(message) {
    try {
        await axios.post(discordWebhook, { content: message });
    } catch (err) {
        console.error("❌ Discord Webhook Error:", err.response?.data || err.message);
    }
}

// Get Roblox userId from username
async function getUserId(username) {
    const res = await axios.get(`https://api.roblox.com/users/get-by-username?username=${username}`);
    return res.data.Id;
}

// Send friend request
async function sendFriendRequest(targetUserId) {
    await axios.post(`https://friends.roblox.com/v1/users/${targetUserId}/request-friendship`, {}, {
        headers: { Cookie: `.ROBLOSECURITY=${cookie}` }
    });
    await sendToDiscord(`✅ Friend request sent to ${mainUsername}`);
}

// Get presence (check if in-game)
async function getPresence(userId) {
    const res = await axios.post(`https://presence.roblox.com/v1/presence/users`, { userIds: [userId] }, {
        headers: { Cookie: `.ROBLOSECURITY=${cookie}` }
    });
    return res.data.userPresences[0];
}

// Join a game
async function joinGame(placeId, jobId) {
    await sendToDiscord(`🎮 Joining PlaceId: ${placeId} | JobId: ${jobId}`);
}

(async () => {
    mainUserId = await getUserId(mainUsername);

    await sendFriendRequest(mainUserId);

    await sendToDiscord(`🤖 Bot started. Watching ${mainUsername}...`);

    setInterval(async () => {
        try {
            const presence = await getPresence(mainUserId);

            if (presence.userPresenceType === 2) { // 2 = In Game
                await joinGame(presence.placeId, presence.gameId);
            }
        } catch (err) {
            console.error("Error:", err.response?.data || err.message);
        }
    }, 10000);
})();
