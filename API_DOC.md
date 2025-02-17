# 卡密系统 API 文档

## API 基本信息

- 基础URL: `http://localhost:8888`
- 响应格式: JSON
- 编码方式: UTF-8
- 设备限制: 每个卡密可设置最大设备数量

## API 接口列表

### 1. 验证卡密

验证卡密的有效性并返回剩余时间。系统会自动识别设备标识，根据卡密设置的最大设备数量限制使用。

**接口地址**
```
POST /api/verify_card
```

**请求头**
```
Content-Type: application/json
```

**请求体**
```json
{
    "card_key": "your_card_key"  // 要验证的卡密
}
```

**响应参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| valid | boolean | 卡密是否有效 |
| remaining_minutes | integer | 剩余有效分钟数 |
| message | string | 状态说明信息 |

**响应示例**

```json
// 成功响应 - 首次使用卡密
{
    "valid": true,
    "remaining_minutes": 60,
    "message": "卡密首次使用成功"
}

// 成功响应 - 已使用但未过期的卡密
{
    "valid": true,
    "remaining_minutes": 30,
    "message": "卡密有效"
}

// 失败响应 - 超出设备数量限制
{
    "valid": false,
    "message": "超出最大设备数量限制（X台设备）"
}

// 失败响应 - 卡密不存在
{
    "valid": false,
    "message": "卡密不存在"
}

// 失败响应 - 卡密已过期
{
    "valid": false,
    "remaining_minutes": 0,
    "message": "卡密已过期"
}
```

**状态码说明**

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 403 | 设备数量超限 |
| 404 | 卡密不存在 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |

## 开发示例

### Python 示例
```python
import requests

def verify_card(card_key):
    url = "http://localhost:8888/api/verify_card"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "card_key": card_key
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 403:
            print("超出设备数量限制")
            return False
            
        response.raise_for_status()
        
        data = response.json()
        if data["valid"]:
            print(f"卡密验证成功！剩余时间：{data['remaining_minutes']}分钟")
            return True
        else:
            print(f"卡密验证失败：{data['message']}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"请求失败：{str(e)}")
        return False

# 使用示例
card_key = "your_card_key"
verify_card(card_key)
```

### JavaScript 示例
```javascript
async function verifyCard(cardKey) {
    try {
        const response = await fetch('http://localhost:8888/api/verify_card', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                card_key: cardKey
            })
        });
        
        const data = await response.json();
        
        if (data.valid) {
            console.log(`卡密验证成功！剩余时间：${data.remaining_minutes}分钟`);
            return true;
        } else {
            console.log(`卡密验证失败：${data.message}`);
            return false;
        }
    } catch (error) {
        console.error('请求失败：', error);
        return false;
    }
}

// 使用示例
const cardKey = 'your_card_key';
verifyCard(cardKey);
```

## 注意事项

1. **设备识别**
   - 系统通过请求头中的User-Agent和客户端IP识别设备
   - 设备标识一旦生成将与卡密绑定
   - 同一设备多次使用相同卡密不会重复计数

2. **时间计算**
   - 卡密激活后立即开始计时
   - 剩余时间精确到分钟
   - 过期后将无法继续使用

3. **设备限制**
   - 每个卡密可设置最大允许设备数
   - 超出限制后将无法在新设备上使用
   - 已添加的设备不受影响

4. **安全建议**
   - 在生产环境中使用HTTPS
   - 实现请求重试机制
   - 添加适当的错误处理
   - 注意频率限制

5. **最佳实践**
   - 定期检查卡密状态
   - 在到期前提醒用户
   - 保存设备标识信息
   - 添加日志记录

## 更新日志

### v1.2.0 (2024-02-18)
- 优化卡密状态显示
- 添加实时倒计时功能
- 增加剩余时间的精确显示（时分秒）
- 改进过期状态判断逻辑

### v1.1.0 (2024-02-17)
- 添加设备限制功能
- 增加设备识别机制
- 新增403状态码处理

### v1.0.0 (2024-02-17)
- 初始版本发布
- 基本卡密验证功能
- 时间限制功能

## 状态说明

卡密可能存在以下几种状态：

1. **未使用**
   - 卡密尚未被激活
   - `valid` 为 true
   - `remaining_minutes` 为初始设置时间

2. **使用中**
   - 卡密已激活且未过期
   - `valid` 为 true
   - `remaining_minutes` 为实时剩余分钟数
   - 支持精确到秒的倒计时显示

3. **已过期**
   - 卡密已超过有效期
   - `valid` 为 false
   - `remaining_minutes` 为 0

4. **设备冲突**
   - 卡密被其他设备使用
   - `valid` 为 false
   - 返回403状态码

## 客户端建议

1. **倒计时显示**
   - 建议在客户端实现实时倒计时显示
   - 可参考以下JavaScript代码实现倒计时：

```javascript
function updateCountdown(expirationTime) {
    const now = new Date();
    const expiration = new Date(expirationTime);
    
    if (now >= expiration) {
        return '已过期';
    }
    
    const remainingTime = expiration - now;
    const hours = Math.floor(remainingTime / (1000 * 60 * 60));
    const minutes = Math.floor((remainingTime % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((remainingTime % (1000 * 60)) / 1000);
    
    return `${hours}时${minutes}分${seconds}秒`;
}

// 使用示例
setInterval(() => {
    const countdown = updateCountdown(expirationTime);
    document.getElementById('countdown').textContent = countdown;
}, 1000);
```

2. **状态更新**
   - 定期检查卡密状态（建议30秒-1分钟间隔）
   - 实现优雅的过期处理
   - 注意处理设备识别相关的错误 